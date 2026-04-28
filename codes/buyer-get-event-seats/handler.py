import json
import os
import logging
from decimal import Decimal
import boto3

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
    """Trae la información de un evento específico y sus asientos."""
    logger.info("GET /buyer/events/{eventId} - Traer evento y asientos")

    try:
        event_id = event.get("pathParameters", {}).get("eventId")
        if not event_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "eventId es requerido"}),
            }

        # Obtener metadata del evento desde Aurora
        aurora_response = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                SELECT e.id, e.name, e.description, e.event_date, e.event_time,
                       e.total_seats, e.status,
                       l.name AS location_name, l.address AS location_address,
                       o.name AS organizer_name
                FROM events e
                LEFT JOIN locations l ON e.location_id = l.id
                LEFT JOIN organizers o ON e.organizer_id = o.id
                WHERE e.id = :event_id
            """,
            parameters=[
                {"name": "event_id", "value": {"stringValue": event_id}},
            ],
        )

        records = aurora_response.get("records", [])
        if not records:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Evento no encontrado"}),
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
            "location_name": record[7].get("stringValue", ""),
            "location_address": record[8].get("stringValue", ""),
            "organizer_name": record[9].get("stringValue", ""),
        }

        # Obtener asientos desde DynamoDB
        seats_table = dynamodb.Table(SEATS_TABLE)
        seats_response = seats_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("event_id").eq(event_id)
        )

        seats = []
        for seat in seats_response.get("Items", []):
            seats.append({
                "seat_id": seat.get("seat_id"),
                "section": seat.get("section", ""),
                "row": seat.get("row", ""),
                "number": seat.get("number", ""),
                "status": seat.get("status", "available"),
                "price": str(seat.get("price", 0)),
            })

        event_info["seats"] = seats

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"event": event_info}, default=str),
        }

    except Exception as e:
        logger.error(f"Error al obtener evento y asientos: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al obtener el evento"}),
        }
