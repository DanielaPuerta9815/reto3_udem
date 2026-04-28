import json
import os
import logging
import uuid
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

rds_client = boto3.client("rds-data")

AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]
EVENTBRIDGE_BUS_NAME = os.environ["EVENTBRIDGE_BUS_NAME"]
STAGE = os.environ["STAGE"]


def lambda_handler(event, context):
    """Crea una alerta o campaña asociada a un evento del organizador."""
    logger.info("POST /organizer/alerts - Crear alerta/campaña")

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
        body = json.loads(event.get("body", "{}"))
        organizer_id = body.get("organizer_id")
        event_id = body.get("event_id")
        alert_type = body.get("alert_type", "campaign")
        title = body.get("title")
        message = body.get("message")
        target_audience = body.get("target_audience", "all")

        if not all([organizer_id, event_id, title, message]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "error": "organizer_id, event_id, title y message son requeridos"
                }),
            }

        valid_types = ["campaign", "reminder", "promotion", "announcement"]
        if alert_type not in valid_types:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "error": f"alert_type invalido. Valores permitidos: {', '.join(valid_types)}"
                }),
            }

        # Verificar que el evento pertenece al organizador
        aurora_response = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="SELECT id FROM events WHERE id = :event_id AND organizer_id = :organizer_id",
            parameters=[
                {"name": "event_id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
            ],
        )

        if not aurora_response.get("records"):
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado o no pertenece a este organizador"}),
            }

        alert_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Guardar la alerta/campaña en Aurora
        rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                INSERT INTO alerts (id, event_id, organizer_id, alert_type, title,
                                    message, target_audience, status, created_at)
                VALUES (:id, :event_id, :organizer_id, :alert_type, :title,
                        :message, :target_audience, 'active', :created_at)
            """,
            parameters=[
                {"name": "id", "value": {"stringValue": alert_id}},
                {"name": "event_id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
                {"name": "alert_type", "value": {"stringValue": alert_type}},
                {"name": "title", "value": {"stringValue": title}},
                {"name": "message", "value": {"stringValue": message}},
                {"name": "target_audience", "value": {"stringValue": target_audience}},
                {"name": "created_at", "value": {"stringValue": now}},
            ],
        )

        # Opcionalmente enviar notificación via EventBridge
        events_client = boto3.client("events")
        events_client.put_events(
            Entries=[
                {
                    "Source": f"reto3.{STAGE}.organizer",
                    "DetailType": "AlertCreated",
                    "Detail": json.dumps({
                        "alert_id": alert_id,
                        "event_id": event_id,
                        "organizer_id": organizer_id,
                        "alert_type": alert_type,
                        "title": title,
                        "target_audience": target_audience,
                        "created_at": now,
                    }),
                    "EventBusName": EVENTBRIDGE_BUS_NAME,
                }
            ]
        )

        logger.info(f"Alerta creada: {alert_id} para evento {event_id} por organizador {organizer_id}")

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Alerta/campaña creada exitosamente",
                "alert": {
                    "id": alert_id,
                    "event_id": event_id,
                    "alert_type": alert_type,
                    "title": title,
                    "status": "active",
                    "created_at": now,
                },
            }),
        }

    except Exception as e:
        logger.error(f"Error al crear alerta: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al crear la alerta"}),
        }
