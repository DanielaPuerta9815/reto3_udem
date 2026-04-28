import json
import os
import logging
from decimal import Decimal
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
    """Trae la información y asientos de un evento específico del organizador."""
    logger.info("GET /organizer/events/{eventId} - Traer evento y asientos del organizador")

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

        # Verificar que el evento pertenece al organizador
        aurora_response = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                SELECT e.id, e.name, e.description, e.event_date, e.event_time,
                       e.total_seats, e.status, e.created_at,
                       l.name AS location_name, l.address AS location_address,
                       l.capacity AS location_capacity
                FROM events e
                LEFT JOIN locations l ON e.location_id = l.id
                WHERE e.id = :event_id AND e.organizer_id = :organizer_id
            """,
            parameters=[
                {"name": "event_id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
            ],
        )

        records = aurora_response.get("records", [])
        if not records:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado o no pertenece a este organizador"}),
            }

        record = records[0]
        event_info = {
            "id": str(record[0].get("longValue") or record[0].get("stringValue")),
            "name": record[1].get("stringValue", ""),
            "description": record[2].get("stringValue", ""),
            "event_date": record[3].get("stringValue", ""),
            "event_time": record[4].get("stringValue", ""),
            "total_seats": record[5].get("longValue", 0),
            "status": record[6].get("stringValue", ""),
            "created_at": record[7].get("stringValue", ""),
            "location_name": record[8].get("stringValue", ""),
            "location_address": record[9].get("stringValue", ""),
            "location_capacity": record[10].get("longValue", 0),
        }

        # Obtener todos los asientos desde DynamoDB
        seats_table = dynamodb.Table(SEATS_TABLE)
        seats_response = seats_table.query(
            KeyConditionExpression=Key("event_id").eq(event_id)
        )

        seats = []
        stats = {"available": 0, "reserved": 0, "attended": 0}
        for seat in seats_response.get("Items", []):
            status = seat.get("status", "available")
            stats[status] = stats.get(status, 0) + 1
            seats.append({
                "seat_id": seat.get("seat_id"),
                "section": seat.get("section", ""),
                "row": seat.get("row", ""),
                "number": seat.get("number", ""),
                "status": status,
                "price": str(seat.get("price", 0)),
                "user_id": seat.get("user_id", None),
                "reserved_at": seat.get("reserved_at", None),
                "attended_at": seat.get("attended_at", None),
            })

        event_info["seats"] = seats
        event_info["stats"] = stats

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"event": event_info}, default=str),
        }

    except Exception as e:
        logger.error(f"Error al obtener evento del organizador: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al obtener el evento"}),
        }
