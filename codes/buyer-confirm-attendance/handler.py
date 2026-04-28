import json
import os
import logging
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]


def lambda_handler(event, context):
    """Confirma o marca la asistencia de un comprador a un evento."""
    logger.info("POST /buyer/attendance - Confirmar asistencia")

    # Validar grupo del JWT
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", "")
    if "ATTENDEE" not in groups:
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Acceso denegado. Se requiere rol ATTENDEE."}),
        }

    # Extraer user_id del JWT
    user_id = claims.get("sub", "")
    if not user_id:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "No se pudo obtener el user_id del token"}),
        }

    try:
        body = json.loads(event.get("body", "{}"))
        event_id = body.get("event_id")
        seat_id = body.get("seat_id")

        if not all([event_id, seat_id]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "event_id y seat_id son requeridos"}),
            }

        seats_table = dynamodb.Table(SEATS_TABLE)
        now = datetime.utcnow().isoformat()

        # Marcar asistencia (solo si el asiento esta reservado por este usuario)
        try:
            seats_table.update_item(
                Key={"event_id": event_id, "seat_id": seat_id},
                UpdateExpression="SET #s = :attended, attended_at = :ts",
                ConditionExpression="user_id = :uid AND #s = :reserved",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":attended": "attended",
                    ":uid": user_id,
                    ":reserved": "reserved",
                    ":ts": now,
                },
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "No tienes una reserva activa para este asiento"}),
            }

        logger.info(f"Asistencia confirmada: seat_id={seat_id}, event_id={event_id}, user_id={user_id}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Asistencia confirmada exitosamente",
                "event_id": event_id,
                "seat_id": seat_id,
                "user_id": user_id,
                "attended_at": now,
            }),
        }

    except Exception as e:
        logger.error(f"Error al confirmar asistencia: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al confirmar la asistencia"}),
        }
