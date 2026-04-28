import json
import os
import logging
from datetime import datetime, timedelta
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
rds_client = boto3.client("rds-data")
sns_client = boto3.client("sns")

DYNAMODB_SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


def lambda_handler(event, context):
    """Envía recordatorios programados 24h y 12h antes de los eventos."""
    logger.info("Ejecutando verificación de recordatorios programados")

    now = datetime.utcnow()

    # Ventanas de tiempo para recordatorios (±30 minutos para cubrir el intervalo del cron)
    windows = [
        {
            "label": "24 horas",
            "start": now + timedelta(hours=23, minutes=30),
            "end": now + timedelta(hours=24, minutes=30),
        },
        {
            "label": "12 horas",
            "start": now + timedelta(hours=11, minutes=30),
            "end": now + timedelta(hours=12, minutes=30),
        },
    ]

    total_reminders_sent = 0

    for window in windows:
        try:
            start_dt = window["start"].strftime("%Y-%m-%d %H:%M:%S")
            end_dt = window["end"].strftime("%Y-%m-%d %H:%M:%S")

            # Buscar eventos activos en la ventana de tiempo
            aurora_response = rds_client.execute_statement(
                resourceArn=AURORA_CLUSTER_ARN,
                secretArn=AURORA_SECRET_ARN,
                database=AURORA_DB_NAME,
                sql="""
                    SELECT id, name, event_date, event_time
                    FROM events
                    WHERE status = 'active'
                      AND CONCAT(event_date, ' ', event_time) BETWEEN :start_dt AND :end_dt
                """,
                parameters=[
                    {"name": "start_dt", "value": {"stringValue": start_dt}},
                    {"name": "end_dt", "value": {"stringValue": end_dt}},
                ],
            )

            events_found = aurora_response.get("records", [])
            logger.info(f"Recordatorio {window['label']}: {len(events_found)} eventos encontrados")

            for evt in events_found:
                event_id = evt[0].get("stringValue", "")
                event_name = evt[1].get("stringValue", "")
                event_date = evt[2].get("stringValue", "")
                event_time = evt[3].get("stringValue", "")

                # Obtener correos de usuarios con reservas activas
                seats_table = dynamodb.Table(DYNAMODB_SEATS_TABLE)
                seats_response = seats_table.query(
                    KeyConditionExpression=Key("event_id").eq(event_id)
                )

                user_emails = list(set(
                    s.get("user_email") for s in seats_response.get("Items", [])
                    if s.get("status") == "reserved" and s.get("user_email")
                ))

                if user_emails:
                    message = (
                        f"Recordatorio: Faltan {window['label']} para tu evento!\n\n"
                        f"Evento: {event_name}\n"
                        f"Fecha: {event_date}\n"
                        f"Hora: {event_time}\n\n"
                        f"Usuarios notificados: {', '.join(user_emails)}\n\n"
                        f"No olvides asistir!"
                    )

                    sns_client.publish(
                        TopicArn=SNS_TOPIC_ARN,
                        Subject=f"Recordatorio {window['label']} - {event_name}",
                        Message=message,
                    )

                    total_reminders_sent += 1
                    logger.info(
                        f"Recordatorio {window['label']} enviado para evento {event_id} "
                        f"a {len(user_emails)} usuarios"
                    )

        except Exception as e:
            logger.error(f"Error procesando recordatorios de {window['label']}: {str(e)}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Recordatorios procesados",
            "reminders_sent": total_reminders_sent,
        }),
    }
