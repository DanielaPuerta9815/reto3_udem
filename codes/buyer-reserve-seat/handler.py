import json
import os
import logging
import uuid
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
rds_client = boto3.client("rds-data")
events_client = boto3.client("events")

SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]
EVENTBRIDGE_BUS_NAME = os.environ["EVENTBRIDGE_BUS_NAME"]
STAGE = os.environ["STAGE"]


def lambda_handler(event, context):
    """Guarda/Reserva un asiento para un comprador."""
    logger.info("POST /buyer/seats - Reservar asiento")

    # Validar grupo del JWT
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", "")
    if "ATTENDEE" not in groups:
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Acceso denegado. Se requiere rol ATTENDEE."}),
        }

    # Extraer correo del usuario desde el JWT
    user_email = claims.get("email", "")

    try:
        body = json.loads(event.get("body", "{}"))
        event_id = body.get("event_id")
        seat_id = body.get("seat_id")
        user_id = body.get("user_id")

        if not all([event_id, seat_id, user_id]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "event_id, seat_id y user_id son requeridos"}),
            }

        # Verificar que el evento existe y esta activo en Aurora
        aurora_response = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="SELECT id, status, total_seats, name, event_date, event_time FROM events WHERE id = :event_id",
            parameters=[{"name": "event_id", "value": {"stringValue": event_id}}],
        )

        records = aurora_response.get("records", [])
        if not records:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado"}),
            }

        event_status = records[0][1].get("stringValue", "")
        if event_status != "active":
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "El evento no está activo"}),
            }

        event_name = records[0][3].get("stringValue", "")
        event_date = records[0][4].get("stringValue", "")
        event_time = records[0][5].get("stringValue", "")

        # Verificar disponibilidad del asiento en DynamoDB usando conditional write
        seats_table = dynamodb.Table(SEATS_TABLE)

        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        try:
            seats_table.update_item(
                Key={"event_id": event_id, "seat_id": seat_id},
                UpdateExpression="SET #s = :reserved, user_id = :uid, user_email = :email, reservation_id = :rid, reserved_at = :ts",
                ConditionExpression="#s = :available OR attribute_not_exists(#s)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":reserved": "reserved",
                    ":available": "available",
                    ":uid": user_id,
                    ":email": user_email,
                    ":rid": reservation_id,
                    ":ts": now,
                },
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return {
                "statusCode": 409,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "El asiento ya está reservado"}),
            }

        # Actualizar contador en la tabla de eventos
        events_table = dynamodb.Table(EVENTS_TABLE)
        events_table.update_item(
            Key={"event_id": event_id},
            UpdateExpression="SET seats_sold = if_not_exists(seats_sold, :zero) + :one, seats_available = seats_available - :one",
            ExpressionAttributeValues={":one": 1, ":zero": 0},
        )

        # Enviar evento de confirmación de reserva a EventBridge
        try:
            events_client.put_events(
                Entries=[
                    {
                        "Source": f"reto3.{STAGE}.buyer",
                        "DetailType": "SeatReserved",
                        "Detail": json.dumps({
                            "reservation_id": reservation_id,
                            "event_id": event_id,
                            "event_name": event_name,
                            "event_date": event_date,
                            "event_time": event_time,
                            "seat_id": seat_id,
                            "user_id": user_id,
                            "user_email": user_email,
                            "reserved_at": now,
                        }),
                        "EventBusName": EVENTBRIDGE_BUS_NAME,
                    }
                ]
            )
            logger.info(f"Evento SeatReserved enviado a EventBridge para {user_email}")
        except Exception as eb_error:
            logger.error(f"Error al enviar evento a EventBridge: {str(eb_error)}")

        logger.info(f"Asiento {seat_id} reservado para usuario {user_id} en evento {event_id}")

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Asiento reservado exitosamente",
                "reservation": {
                    "reservation_id": reservation_id,
                    "event_id": event_id,
                    "seat_id": seat_id,
                    "user_id": user_id,
                    "status": "reserved",
                    "reserved_at": now,
                },
            }),
        }

    except Exception as e:
        logger.error(f"Error al reservar asiento: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al reservar el asiento"}),
        }
