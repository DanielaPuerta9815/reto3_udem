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
    """Trae todos los eventos de un organizador específico."""
    logger.info("GET /organizer/events - Traer todos los eventos del organizador")

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
        # El organizer_id viene del JWT (sub del token)
        organizer_id = claims.get("sub", "")

        if not organizer_id:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "No se pudo obtener el organizer_id del token"}),
            }

        # Obtener eventos del organizador desde Aurora
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
                WHERE e.organizer_id = :organizer_id
                ORDER BY e.event_date DESC
            """,
            parameters=[
                {"name": "organizer_id", "value": {"stringValue": organizer_id}},
            ],
        )

        events = []
        for record in aurora_response.get("records", []):
            event_id = str(record[0].get("longValue") or record[0].get("stringValue"))

            # Consultar datos de ventas en DynamoDB
            table = dynamodb.Table(EVENTS_TABLE)
            dynamo_response = table.get_item(Key={"event_id": event_id})
            dynamo_data = dynamo_response.get("Item", {})

            events.append({
                "id": event_id,
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
            "body": json.dumps({"events": events, "count": len(events)}, default=str),
        }

    except Exception as e:
        logger.error(f"Error al obtener eventos del organizador: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al obtener los eventos"}),
        }
