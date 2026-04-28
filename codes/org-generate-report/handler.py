import json
import os
import logging
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

events_client = boto3.client("events")

EVENTBRIDGE_BUS_NAME = os.environ["EVENTBRIDGE_BUS_NAME"]
STAGE = os.environ["STAGE"]


def lambda_handler(event, context):
    """Genera un reporte sobre un evento enviando un evento a EventBridge."""
    logger.info("POST /organizer/reports - Generar reporte de evento")

    # Validar grupo del JWT y extraer email
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", "")
    if "ORGANIZER" not in groups:
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Acceso denegado. Se requiere rol ORGANIZER."}),
        }

    organizer_email = claims.get("email", "")

    try:
        body = json.loads(event.get("body", "{}"))
        event_id = body.get("event_id")
        organizer_id = body.get("organizer_id")
        report_type = body.get("report_type", "general")

        if not all([event_id, organizer_id]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "event_id y organizer_id son requeridos"}),
            }

        valid_report_types = ["general", "attendance", "sales", "occupancy"]
        if report_type not in valid_report_types:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "error": f"report_type invalido. Valores permitidos: {', '.join(valid_report_types)}"
                }),
            }

        now = datetime.utcnow().isoformat()

        # Enviar evento a EventBridge para que otro servicio procese el reporte
        response = events_client.put_events(
            Entries=[
                {
                    "Source": f"reto3.{STAGE}.organizer",
                    "DetailType": "ReportRequested",
                    "Detail": json.dumps({
                        "event_id": event_id,
                        "organizer_id": organizer_id,
                        "organizer_email": organizer_email,
                        "report_type": report_type,
                        "requested_at": now,
                        "stage": STAGE,
                        "filters": body.get("filters", {}),
                    }),
                    "EventBusName": EVENTBRIDGE_BUS_NAME,
                }
            ]
        )

        failed_count = response.get("FailedEntryCount", 0)
        if failed_count > 0:
            logger.error(f"EventBridge: {failed_count} entradas fallaron: {response.get('Entries', [])}")
            return {
                "statusCode": 502,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Error al enviar solicitud de reporte"}),
            }

        logger.info(f"Reporte solicitado: type={report_type}, event_id={event_id}, organizer={organizer_id}")

        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Solicitud de reporte enviada exitosamente. El reporte se procesará en segundo plano.",
                "report": {
                    "event_id": event_id,
                    "report_type": report_type,
                    "status": "processing",
                    "requested_at": now,
                },
            }),
        }

    except Exception as e:
        logger.error(f"Error al generar reporte: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al generar el reporte"}),
        }
