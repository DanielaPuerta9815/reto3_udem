import json
import os
import logging
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

rds_client = boto3.client("rds-data")
dynamodb = boto3.resource("dynamodb")
events_client = boto3.client("events")

AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]
DYNAMODB_SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
EVENTBRIDGE_BUS_NAME = os.environ["EVENTBRIDGE_BUS_NAME"]
STAGE = os.environ["STAGE"]


def lambda_handler(event, context):
    """Edita un evento existente del organizador."""
    logger.info("PUT /organizer/events/{eventId} - Editar evento")

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
        if not event_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "eventId es requerido"}),
            }

        body = json.loads(event.get("body", "{}"))
        organizer_id = body.get("organizer_id")

        if not organizer_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "organizer_id es requerido"}),
            }

        # Construir la consulta UPDATE dinámicamente
        updatable_fields = {
            "name": "stringValue",
            "description": "stringValue",
            "event_date": "stringValue",
            "event_time": "stringValue",
            "status": "stringValue",
        }

        set_clauses = []
        parameters = [
            {"name": "event_id", "value": {"stringValue": event_id}},
            {"name": "organizer_id", "value": {"stringValue": organizer_id}},
        ]

        for field, value_type in updatable_fields.items():
            if field in body:
                set_clauses.append(f"{field} = :{field}")
                parameters.append({
                    "name": field,
                    "value": {value_type: str(body[field])},
                })

        if not set_clauses:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "No se proporcionaron campos para actualizar"}),
            }

        set_clauses.append("updated_at = NOW()")
        sql = f"UPDATE events SET {', '.join(set_clauses)} WHERE id = :event_id AND organizer_id = :organizer_id"

        result = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql=sql,
            parameters=parameters,
        )

        if result.get("numberOfRecordsUpdated", 0) == 0:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado o no pertenece a este organizador"}),
            }

        # Obtener nombre del evento actualizado
        event_info = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="SELECT name FROM events WHERE id = :event_id",
            parameters=[{"name": "event_id", "value": {"stringValue": event_id}}],
        )
        event_name = ""
        if event_info.get("records"):
            event_name = event_info["records"][0][0].get("stringValue", "")

        # Obtener correos de usuarios con reservas activas para notificar
        seats_table = dynamodb.Table(DYNAMODB_SEATS_TABLE)
        seats_response = seats_table.query(
            KeyConditionExpression=Key("event_id").eq(event_id)
        )
        user_emails = list(set(
            s.get("user_email") for s in seats_response.get("Items", [])
            if s.get("status") == "reserved" and s.get("user_email")
        ))

        # Enviar evento de actualización a EventBridge para notificar a usuarios registrados
        if user_emails:
            try:
                events_client.put_events(
                    Entries=[
                        {
                            "Source": f"reto3.{STAGE}.organizer",
                            "DetailType": "EventUpdated",
                            "Detail": json.dumps({
                                "event_id": event_id,
                                "event_name": event_name,
                                "updated_fields": [f for f in body.keys() if f != "organizer_id"],
                                "user_emails": user_emails,
                            }),
                            "EventBusName": EVENTBRIDGE_BUS_NAME,
                        }
                    ]
                )
                logger.info(f"Evento EventUpdated enviado a EventBridge para {len(user_emails)} usuarios")
            except Exception as eb_error:
                logger.error(f"Error al enviar evento a EventBridge: {str(eb_error)}")

        logger.info(f"Evento editado: {event_id} por organizador {organizer_id}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Evento actualizado exitosamente",
                "event_id": event_id,
                "updated_fields": list(body.keys()),
            }),
        }

    except Exception as e:
        logger.error(f"Error al editar evento: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al editar el evento"}),
        }
