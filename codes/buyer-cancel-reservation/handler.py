import json
import os
import logging
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]


def lambda_handler(event, context):
    """Elimina o cancela la reserva de un asiento."""
    logger.info("DELETE /buyer/seats/{seatId} - Cancelar reserva")

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
        seat_id = event.get("pathParameters", {}).get("seatId")
        if not seat_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "seatId es requerido"}),
            }

        # event_id viene como query param en un DELETE
        query_params = event.get("queryStringParameters") or {}
        event_id = query_params.get("event_id")

        if not event_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "event_id es requerido como query parameter"}),
            }

        seats_table = dynamodb.Table(SEATS_TABLE)
        now = datetime.utcnow().isoformat()

        # Cancelar la reserva (solo si pertenece al usuario)
        try:
            seats_table.update_item(
                Key={"event_id": event_id, "seat_id": seat_id},
                UpdateExpression="SET #s = :available, cancelled_at = :ts REMOVE user_id, reservation_id, reserved_at",
                ConditionExpression="user_id = :uid AND #s = :reserved",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":available": "available",
                    ":uid": user_id,
                    ":reserved": "reserved",
                    ":ts": now,
                },
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "No tienes permiso para cancelar esta reserva o ya fue cancelada"}),
            }

        # Actualizar contadores del evento
        events_table = dynamodb.Table(EVENTS_TABLE)
        events_table.update_item(
            Key={"event_id": event_id},
            UpdateExpression="SET seats_sold = seats_sold - :one, seats_available = seats_available + :one",
            ExpressionAttributeValues={":one": 1},
        )

        logger.info(f"Reserva cancelada: seat_id={seat_id}, event_id={event_id}, user_id={user_id}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Reserva cancelada exitosamente",
                "seat_id": seat_id,
                "event_id": event_id,
                "cancelled_at": now,
            }),
        }

    except Exception as e:
        logger.error(f"Error al cancelar reserva: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al cancelar la reserva"}),
        }
