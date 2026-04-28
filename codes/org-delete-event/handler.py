import json
import os
import logging
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
rds_client = boto3.client("rds-data")
events_client = boto3.client("events")

EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]
SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]
EVENTBRIDGE_BUS_NAME = os.environ["EVENTBRIDGE_BUS_NAME"]
STAGE = os.environ["STAGE"]


def lambda_handler(event, context):
    """Cancela un evento del organizador (soft delete + notificación a usuarios registrados)."""
    logger.info("DELETE /organizer/events/{eventId} - Eliminar/Cancelar evento")

    # Validar grupo del JWT
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", "")
    if "ORGANIZER" not in groups:
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Acceso denegado. Se requiere rol ORGANIZER."}),
        }

    try:
        event_id = event.get("pathParameters", {}).get("eventId")
        organizer_id = claims.get("sub", "")

        if not event_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "eventId es requerido"}),
            }

        if not organizer_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "No se pudo obtener el organizer_id del token"}),
            }

        # Obtener nombre del evento antes de cancelar
        event_info = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="SELECT name FROM events WHERE id = :event_id AND organizer_id = :organizer_id AND status != 'deleted'",
            parameters=[
                {"name": "event_id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
            ],
        )

        if not event_info.get("records"):
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado o no pertenece a este organizador"}),
            }

        event_name = event_info["records"][0][0].get("stringValue", "")

        # Obtener asientos reservados y correos de usuarios para notificación
        seats_table = dynamodb.Table(SEATS_TABLE)
        seats_response = seats_table.query(
            KeyConditionExpression=Key("event_id").eq(event_id)
        )

        user_emails = list(set(
            s.get("user_email") for s in seats_response.get("Items", [])
            if s.get("status") == "reserved" and s.get("user_email")
        ))

        # Soft delete en Aurora (cambiar status a 'deleted')
        result = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                UPDATE events SET status = 'deleted', updated_at = NOW()
                WHERE id = :event_id AND organizer_id = :organizer_id AND status != 'deleted'
            """,
            parameters=[
                {"name": "event_id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
            ],
        )

        if result.get("numberOfRecordsUpdated", 0) == 0:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado o no pertenece a este organizador"}),
            }

        # Enviar notificación de cancelación a usuarios registrados via EventBridge
        if user_emails:
            try:
                events_client.put_events(
                    Entries=[
                        {
                            "Source": f"reto3.{STAGE}.organizer",
                            "DetailType": "EventCancelled",
                            "Detail": json.dumps({
                                "event_id": event_id,
                                "event_name": event_name,
                                "user_emails": user_emails,
                            }),
                            "EventBusName": EVENTBRIDGE_BUS_NAME,
                        }
                    ]
                )
                logger.info(f"Evento EventCancelled enviado a EventBridge para {len(user_emails)} usuarios")
            except Exception as eb_error:
                logger.error(f"Error al enviar evento a EventBridge: {str(eb_error)}")

        # Limpiar asientos de DynamoDB
        with seats_table.batch_writer() as batch:
            for seat in seats_response.get("Items", []):
                batch.delete_item(
                    Key={
                        "event_id": event_id,
                        "seat_id": seat["seat_id"],
                    }
                )

        # Eliminar registro de contadores en DynamoDB
        events_table = dynamodb.Table(EVENTS_TABLE)
        events_table.delete_item(Key={"event_id": event_id})

        logger.info(f"Evento eliminado: {event_id} por organizador {organizer_id}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Evento eliminado exitosamente",
                "event_id": event_id,
                "notified_users": len(user_emails),
            }),
        }

    except Exception as e:
        logger.error(f"Error al eliminar evento: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al eliminar el evento"}),
        }
