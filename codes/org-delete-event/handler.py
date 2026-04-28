import json
import os
import logging
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
rds_client = boto3.client("rds-data")

EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]
SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]


def lambda_handler(event, context):
    """Elimina un evento del organizador (soft delete + limpieza DynamoDB)."""
    logger.info("DELETE /organizer/events/{eventId} - Eliminar evento")

    try:
        event_id = event.get("pathParameters", {}).get("eventId")
        query_params = event.get("queryStringParameters") or {}
        organizer_id = query_params.get("organizer_id")

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
                "body": json.dumps({"error": "organizer_id es requerido"}),
            }

        # Verificar que no tenga reservas activas
        seats_table = dynamodb.Table(SEATS_TABLE)
        seats_response = seats_table.query(
            KeyConditionExpression=Key("event_id").eq(event_id)
        )

        active_reservations = [
            s for s in seats_response.get("Items", [])
            if s.get("status") == "reserved"
        ]

        if active_reservations:
            return {
                "statusCode": 409,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "error": "No se puede eliminar el evento porque tiene reservas activas",
                    "active_reservations": len(active_reservations),
                }),
            }

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
            }),
        }

    except Exception as e:
        logger.error(f"Error al eliminar evento: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al eliminar el evento"}),
        }
