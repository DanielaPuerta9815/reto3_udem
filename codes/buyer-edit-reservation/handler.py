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
    """Edita la reserva de un asiento (por ejemplo, cambiar de asiento)."""
    logger.info("PUT /buyer/seats/{seatId} - Editar reserva")

    try:
        seat_id = event.get("pathParameters", {}).get("seatId")
        if not seat_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "seatId es requerido"}),
            }

        body = json.loads(event.get("body", "{}"))
        event_id = body.get("event_id")
        user_id = body.get("user_id")
        new_seat_id = body.get("new_seat_id")

        if not all([event_id, user_id]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "event_id y user_id son requeridos"}),
            }

        seats_table = dynamodb.Table(SEATS_TABLE)
        now = datetime.utcnow().isoformat()

        # Si se proporciona un nuevo asiento, realizar el cambio
        if new_seat_id and new_seat_id != seat_id:
            # Liberar el asiento actual (solo si pertenece al usuario)
            try:
                seats_table.update_item(
                    Key={"event_id": event_id, "seat_id": seat_id},
                    UpdateExpression="SET #s = :available REMOVE user_id, reservation_id, reserved_at",
                    ConditionExpression="user_id = :uid AND #s = :reserved",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":available": "available",
                        ":uid": user_id,
                        ":reserved": "reserved",
                    },
                )
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                return {
                    "statusCode": 403,
                    "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "No tienes permiso para modificar esta reserva"}),
                }

            # Reservar el nuevo asiento
            try:
                current_item = seats_table.get_item(
                    Key={"event_id": event_id, "seat_id": seat_id}
                ).get("Item", {})
                reservation_id = current_item.get("reservation_id", "")

                seats_table.update_item(
                    Key={"event_id": event_id, "seat_id": new_seat_id},
                    UpdateExpression="SET #s = :reserved, user_id = :uid, reservation_id = :rid, reserved_at = :ts",
                    ConditionExpression="#s = :available OR attribute_not_exists(#s)",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":reserved": "reserved",
                        ":available": "available",
                        ":uid": user_id,
                        ":rid": reservation_id,
                        ":ts": now,
                    },
                )
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                # Revertir: volver a reservar el asiento original
                seats_table.update_item(
                    Key={"event_id": event_id, "seat_id": seat_id},
                    UpdateExpression="SET #s = :reserved, user_id = :uid, reserved_at = :ts",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":reserved": "reserved",
                        ":uid": user_id,
                        ":ts": now,
                    },
                )
                return {
                    "statusCode": 409,
                    "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "El nuevo asiento no está disponible"}),
                }

            final_seat_id = new_seat_id
        else:
            # Solo actualizar datos de la reserva actual
            try:
                update_expressions = []
                expression_values = {}

                if body.get("notes"):
                    update_expressions.append("notes = :notes")
                    expression_values[":notes"] = body["notes"]

                update_expressions.append("updated_at = :ts")
                expression_values[":ts"] = now
                expression_values[":uid"] = user_id
                expression_values[":reserved"] = "reserved"

                seats_table.update_item(
                    Key={"event_id": event_id, "seat_id": seat_id},
                    UpdateExpression=f"SET {', '.join(update_expressions)}",
                    ConditionExpression="user_id = :uid AND #s = :reserved",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues=expression_values,
                )
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                return {
                    "statusCode": 403,
                    "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "No tienes permiso para modificar esta reserva"}),
                }

            final_seat_id = seat_id

        logger.info(f"Reserva editada: seat_id={final_seat_id}, user_id={user_id}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Reserva actualizada exitosamente",
                "seat_id": final_seat_id,
                "event_id": event_id,
                "updated_at": now,
            }),
        }

    except Exception as e:
        logger.error(f"Error al editar reserva: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al editar la reserva"}),
        }
