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
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]


def lambda_handler(event, context):
    """Trae todos los eventos disponibles para los compradores."""
    logger.info("GET /buyer/events - Traer todos los eventos")

    try:
        # Obtener metadata de eventos desde Aurora (nombre, descripcion, locacion, fecha, etc.)
        aurora_response = rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                SELECT e.id, e.name, e.description, e.event_date, e.event_time,
                       e.total_seats, e.status,
                       l.name AS location_name, l.address AS location_address
                FROM events e
                LEFT JOIN locations l ON e.location_id = l.id
                WHERE e.status = 'active'
                ORDER BY e.event_date ASC
            """,
        )

        events = []
        for record in aurora_response.get("records", []):
            event_id = record[0].get("longValue") or record[0].get("stringValue")

            # Consultar asientos vendidos/reservados en DynamoDB
            table = dynamodb.Table(EVENTS_TABLE)
            dynamo_response = table.get_item(Key={"event_id": str(event_id)})
            dynamo_data = dynamo_response.get("Item", {})

            events.append({
                "id": str(event_id),
                "name": record[1].get("stringValue", ""),
                "description": record[2].get("stringValue", ""),
                "event_date": record[3].get("stringValue", ""),
                "event_time": record[4].get("stringValue", ""),
                "total_seats": record[5].get("longValue", 0),
                "status": record[6].get("stringValue", ""),
                "location_name": record[7].get("stringValue", ""),
                "location_address": record[8].get("stringValue", ""),
                "seats_sold": dynamo_data.get("seats_sold", 0),
                "seats_available": dynamo_data.get("seats_available", 0),
            })

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"events": events}, default=str),
        }

    except Exception as e:
        logger.error(f"Error al obtener eventos: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al obtener los eventos"}),
        }
