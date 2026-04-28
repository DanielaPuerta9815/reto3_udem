# Guía de Pruebas - Reto 3: Plataforma de Venta y Gestión de Eventos

## Tabla de Contenidos

1. [Requisitos Previos](#1-requisitos-previos)
2. [Obtener las URLs del Proyecto](#2-obtener-las-urls-del-proyecto)
3. [Configuración de Postman](#3-configuración-de-postman)
4. [Datos Precargados en Aurora](#4-datos-precargados-en-aurora)
5. [PARTE 1 - Endpoints del Organizador](#5-parte-1---endpoints-del-organizador)
   - 5.1 [Crear un Evento](#51-crear-un-evento)
   - 5.2 [Obtener Todos los Eventos del Organizador](#52-obtener-todos-los-eventos-del-organizador)
   - 5.3 [Obtener Detalle y Asientos de un Evento](#53-obtener-detalle-y-asientos-de-un-evento)
   - 5.4 [Editar un Evento](#54-editar-un-evento)
   - 5.5 [Crear una Alerta/Campaña](#55-crear-una-alertacampaña)
   - 5.6 [Generar un Reporte](#56-generar-un-reporte)
6. [PARTE 2 - Endpoints del Comprador](#6-parte-2---endpoints-del-comprador)
   - 6.1 [Ver Todos los Eventos Disponibles](#61-ver-todos-los-eventos-disponibles)
   - 6.2 [Ver Detalle y Asientos de un Evento](#62-ver-detalle-y-asientos-de-un-evento)
   - 6.3 [Reservar un Asiento](#63-reservar-un-asiento)
   - 6.4 [Editar una Reserva (Cambiar de Asiento)](#64-editar-una-reserva-cambiar-de-asiento)
   - 6.5 [Cancelar una Reserva](#65-cancelar-una-reserva)
   - 6.6 [Confirmar Asistencia](#66-confirmar-asistencia)
7. [PARTE 3 - WebSocket (Estado de Asiento en Tiempo Real)](#7-parte-3---websocket-estado-de-asiento-en-tiempo-real)
8. [PARTE 4 - Eliminar un Evento](#8-parte-4---eliminar-un-evento)
9. [Flujo de Prueba Completo Sugerido](#9-flujo-de-prueba-completo-sugerido)

---

## 1. Requisitos Previos

- **AWS CLI** configurada con credenciales válidas
- **Postman** instalado (para pruebas HTTP REST)
- **wscat** instalado para pruebas WebSocket (opcional):
  ```bash
  npm install -g wscat
  ```
- Los dos stacks de CloudFormation desplegados:
  1. `reto3-dev-database` (base de datos, DynamoDB, Aurora, S3, EventBridge)
  2. `reto3-dev-app` (Lambdas, API Gateway HTTP y WebSocket)
- Las funciones Lambda empaquetadas y subidas al bucket S3

---

## 2. Obtener las URLs del Proyecto

Ejecuta el siguiente comando para obtener las URLs de los APIs desplegados:

```bash
aws cloudformation describe-stacks \
  --stack-name reto3-dev-app \
  --region us-east-1 \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" \
  --output table \
  --no-cli-pager
```

Busca en la salida:

| Output Key     | Ejemplo de Valor                                             |
| -------------- | ------------------------------------------------------------ |
| `HttpApiUrl`   | `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev` |
| `WebSocketUrl` | `wss://yyyyyyyyyy.execute-api.us-east-1.amazonaws.com/dev`   |

| Output Key     | Ejemplo de Valor                                             |
| -------------- | ------------------------------------------------------------ |
| `HttpApiUrl`   | `https://taxdch5xr6.execute-api.us-east-1.amazonaws.com/dev` |
| `WebSocketUrl` | `wss://mhgmej0roi.execute-api.us-east-1.amazonaws.com/dev`   |

> **Nota:** A lo largo de esta guía se usará `{{BASE_URL}}` como placeholder para el valor de `HttpApiUrl` y `{{WS_URL}}` para el de `WebSocketUrl`. Reemplaza estos valores con los que obtengas de tu stack.

---

## 3. Configuración de Postman

### Crear una Variable de Entorno

1. En Postman, ve a **Environments** > **Create Environment**
2. Nombra el entorno: `Reto3 - Dev`
3. Agrega las siguientes variables:

| Variable   | Valor                                                        |
| ---------- | ------------------------------------------------------------ |
| `BASE_URL` | `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev` |
| `EVENT_ID` | _(se llenará después de crear un evento)_                    |
| `SEAT_ID`  | _(se llenará después de reservar)_                           |

4. Selecciona este entorno como activo

### Headers Comunes

Para todas las peticiones que envían body (POST, PUT), configura:

| Header         | Valor              |
| -------------- | ------------------ |
| `Content-Type` | `application/json` |

---

## 4. Datos Precargados en Aurora

El stack `reto3-dev-database` inicializa automáticamente las siguientes tablas en Aurora MySQL con datos de prueba:

### Organizadores

| id        | name                 | email                   | phone         |
| --------- | -------------------- | ----------------------- | ------------- |
| `org-001` | Eventos Colombia SAS | contacto@eventoscol.com | +573001234567 |
| `org-002` | Live Shows Latam     | info@liveshows.co       | +573009876543 |

### Locaciones

| id        | name                   | address                     | city     | capacity |
| --------- | ---------------------- | --------------------------- | -------- | -------- |
| `loc-001` | Movistar Arena         | Calle 63 #59A-06, Bogota    | Bogota   | 14000    |
| `loc-002` | Teatro Metropolitan    | Calle 32 #6-40, Bogota      | Bogota   | 1200     |
| `loc-003` | Centro de Convenciones | Carrera 37 #24-67, Medellin | Medellin | 5000     |

> Estos IDs se usarán en las pruebas para crear eventos.

---

## 5. PARTE 1 - Endpoints del Organizador

### 5.1 Crear un Evento

Crea un evento con 10 asientos para que las pruebas posteriores sean rápidas.

| Campo   | Valor                            |
| ------- | -------------------------------- |
| Método  | `POST`                           |
| URL     | `{{BASE_URL}}/organizer/events`  |
| Headers | `Content-Type: application/json` |

**Body (raw JSON):**

```json
{
  "organizer_id": "org-001",
  "name": "Concierto de Rock 2026",
  "description": "Gran concierto de rock en Bogotá con artistas nacionales e internacionales",
  "event_date": "2026-06-15",
  "event_time": "19:00",
  "total_seats": 10,
  "location_id": "loc-001",
  "default_section": "general",
  "price": 50000
}
```

**Respuesta esperada (201 Created):**

```json
{
  "message": "Evento creado exitosamente",
  "event": {
    "id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
    "name": "Concierto de Rock 2026",
    "total_seats": 10,
    "status": "active"
  }
}
```

> **IMPORTANTE:** Copia el valor de `event.id` de la respuesta y guárdalo en la variable de Postman `EVENT_ID`. Este ID se usará en todos los pasos siguientes.

---

### 5.2 Obtener Todos los Eventos del Organizador

| Campo   | Valor                                                |
| ------- | ---------------------------------------------------- |
| Método  | `GET`                                                |
| URL     | `{{BASE_URL}}/organizer/events?organizer_id=org-001` |
| Headers | Ninguno adicional                                    |
| Body    | Ninguno                                              |

**Respuesta esperada (200 OK):**

```json
{
  "events": [
    {
      "id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
      "name": "Concierto de Rock 2026",
      "description": "Gran concierto de rock en Bogotá con artistas nacionales e internacionales",
      "event_date": "2026-06-15",
      "event_time": "19:00",
      "total_seats": 10,
      "status": "active",
      "location_name": "Movistar Arena",
      "location_address": "Calle 63 #59A-06, Bogota",
      "seats_sold": "0",
      "seats_available": "10"
    },
    {
      "id": "9d1a5f5a-e9f0-439f-adbd-55261e8fe8bf",
      "name": "Concierto de Rock 2026",
      "description": "Gran concierto de rock en Bogotá con artistas nacionales e internacionales",
      "event_date": "2026-06-15",
      "event_time": "19:00",
      "total_seats": 10,
      "status": "active",
      "location_name": "Movistar Arena",
      "location_address": "Calle 63 #59A-06, Bogota",
      "seats_sold": "0",
      "seats_available": "10"
    },
    {
      "id": "1ec7eae3-6714-4026-9a0c-b2ae254a5574",
      "name": "Concierto de Rock 2026",
      "description": "Gran concierto de rock en Bogotá con artistas nacionales e internacionales",
      "event_date": "2026-06-15",
      "event_time": "19:00",
      "total_seats": 10,
      "status": "active",
      "location_name": "Movistar Arena",
      "location_address": "Calle 63 #59A-06, Bogota",
      "seats_sold": "0",
      "seats_available": "10"
    }
  ],
  "count": 3
}
```

---

### 5.3 Obtener Detalle y Asientos de un Evento

| Campo   | Valor                                                             |
| ------- | ----------------------------------------------------------------- |
| Método  | `GET`                                                             |
| URL     | `{{BASE_URL}}/organizer/events/{{EVENT_ID}}?organizer_id=org-001` |
| Headers | Ninguno adicional                                                 |
| Body    | Ninguno                                                           |

**Respuesta esperada (200 OK):**

```json
{{
    "event": {
        "id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
        "name": "Concierto de Rock 2026",
        "description": "Gran concierto de rock en Bogotá con artistas nacionales e internacionales",
        "event_date": "2026-06-15",
        "event_time": "19:00",
        "total_seats": 10,
        "status": "active",
        "created_at": "2026-04-25 22:57:15",
        "location_name": "Movistar Arena",
        "location_address": "Calle 63 #59A-06, Bogota",
        "location_capacity": 14000,
        "seats": [
            {
                "seat_id": "seat-0001",
                "section": "general",
                "row": "1",
                "number": "1",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0002",
                "section": "general",
                "row": "1",
                "number": "2",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0003",
                "section": "general",
                "row": "1",
                "number": "3",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0004",
                "section": "general",
                "row": "1",
                "number": "4",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0005",
                "section": "general",
                "row": "1",
                "number": "5",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0006",
                "section": "general",
                "row": "1",
                "number": "6",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0007",
                "section": "general",
                "row": "1",
                "number": "7",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0008",
                "section": "general",
                "row": "1",
                "number": "8",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0009",
                "section": "general",
                "row": "1",
                "number": "9",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            },
            {
                "seat_id": "seat-0010",
                "section": "general",
                "row": "1",
                "number": "10",
                "status": "available",
                "price": "50000",
                "user_id": null,
                "reserved_at": null,
                "attended_at": null
            }
        ],
        "stats": {
            "available": 10,
            "reserved": 0,
            "attended": 0
        }
    }
}
```

> Aquí se pueden ver los `seat_id` generados (seat-0001 hasta seat-0010). Anótalos para las pruebas del comprador.

---

### 5.4 Editar un Evento

| Campo   | Valor                                        |
| ------- | -------------------------------------------- |
| Método  | `PUT`                                        |
| URL     | `{{BASE_URL}}/organizer/events/{{EVENT_ID}}` |
| Headers | `Content-Type: application/json`             |

**Body (raw JSON):**

```json
{
  "organizer_id": "org-001",
  "name": "Concierto de Rock 2026 - Edición Especial",
  "description": "Evento actualizado con artistas sorpresa"
}
```

**Respuesta esperada (200 OK):**

```json
{
  "message": "Evento actualizado exitosamente",
  "event_id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
  "updated_fields": ["organizer_id", "name", "description"]
}
```

---

### 5.5 Crear una Alerta/Campaña

| Campo   | Valor                            |
| ------- | -------------------------------- |
| Método  | `POST`                           |
| URL     | `{{BASE_URL}}/organizer/alerts`  |
| Headers | `Content-Type: application/json` |

**Body (raw JSON):**

```json
{
  "organizer_id": "org-001",
  "event_id": "{{EVENT_ID}}",
  "title": "¡Últimas entradas disponibles!",
  "message": "No te pierdas el Concierto de Rock 2026. Quedan pocas entradas.",
  "alert_type": "promotion",
  "target_audience": "all"
}
```

**Respuesta esperada (201 Created):**

```json
{
  "message": "Alerta/campaña creada exitosamente",
  "alert": {
    "id": "1ef4cc2c-2c4b-4b43-8d76-04ef33745af5",
    "event_id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
    "alert_type": "promotion",
    "title": "¡Últimas entradas disponibles!",
    "status": "active",
    "created_at": "2026-04-25T23:16:23.095710"
  }
}
```

**Valores válidos para `alert_type`:** `campaign`, `reminder`, `promotion`, `announcement`

---

### 5.6 Generar un Reporte

| Campo   | Valor                            |
| ------- | -------------------------------- |
| Método  | `POST`                           |
| URL     | `{{BASE_URL}}/organizer/reports` |
| Headers | `Content-Type: application/json` |

**Body (raw JSON):**

```json
{
  "event_id": "{{EVENT_ID}}",
  "organizer_id": "org-001",
  "report_type": "general"
}
```

**Respuesta esperada (202 Accepted):**

```json
{
  "message": "Solicitud de reporte enviada exitosamente. El reporte se procesará en segundo plano.",
  "report": {
    "event_id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
    "report_type": "general",
    "status": "processing",
    "requested_at": "2026-04-25T23:19:01.603791"
  }
}
```

> Este endpoint envía un evento a EventBridge. El reporte se procesa de forma asíncrona.

**Valores válidos para `report_type`:** `general`, `attendance`, `sales`, `occupancy`

---

## 6. PARTE 2 - Endpoints del Comprador

> **Prerequisito:** Debe existir al menos un evento creado (Paso 5.1). Usa el `EVENT_ID` obtenido anteriormente.

### 6.1 Ver Todos los Eventos Disponibles

| Campo   | Valor                       |
| ------- | --------------------------- |
| Método  | `GET`                       |
| URL     | `{{BASE_URL}}/buyer/events` |
| Headers | Ninguno                     |
| Body    | Ninguno                     |

**Respuesta esperada (200 OK):**

```json
{
  "events": [
    {
      "id": "{{EVENT_ID}}",
      "name": "Concierto de Rock 2026 - Edición Especial",
      "description": "Evento actualizado con artistas sorpresa",
      "event_date": "2026-06-15",
      "event_time": "19:00",
      "total_seats": 10,
      "status": "active",
      "location_name": "Movistar Arena",
      "location_address": "Calle 63 #59A-06, Bogota",
      "seats_sold": 0,
      "seats_available": 10
    }
  ]
}
```

> Solo muestra eventos con status `active`.

---

### 6.2 Ver Detalle y Asientos de un Evento

| Campo   | Valor                                    |
| ------- | ---------------------------------------- |
| Método  | `GET`                                    |
| URL     | `{{BASE_URL}}/buyer/events/{{EVENT_ID}}` |
| Headers | Ninguno                                  |
| Body    | Ninguno                                  |

**Respuesta esperada (200 OK):**

```json
{
  "event": {
    "id": "{{EVENT_ID}}",
    "name": "Concierto de Rock 2026 - Edición Especial",
    "description": "Evento actualizado con artistas sorpresa",
    "event_date": "2026-06-15",
    "event_time": "19:00",
    "total_seats": 10,
    "status": "active",
    "location_name": "Movistar Arena",
    "location_address": "Calle 63 #59A-06, Bogota",
    "organizer_name": "Eventos Colombia SAS",
    "seats": [
      {
        "seat_id": "seat-0001",
        "section": "general",
        "row": "1",
        "number": "1",
        "status": "available",
        "price": "50000"
      },
      {
        "seat_id": "seat-0002",
        "section": "general",
        "row": "1",
        "number": "2",
        "status": "available",
        "price": "50000"
      }
    ]
  }
}
```

> Nota: La respuesta del buyer NO incluye `user_id`, `reserved_at` ni `attended_at` en los asientos (a diferencia del endpoint del organizador).

---

### 6.3 Reservar un Asiento

| Campo   | Valor                            |
| ------- | -------------------------------- |
| Método  | `POST`                           |
| URL     | `{{BASE_URL}}/buyer/seats`       |
| Headers | `Content-Type: application/json` |

**Body (raw JSON):**

```json
{
  "event_id": "{{EVENT_ID}}",
  "seat_id": "seat-0001",
  "user_id": "user-001"
}
```

**Respuesta esperada (201 Created):**

```json
{
  "message": "Asiento reservado exitosamente",
  "reservation": {
    "reservation_id": "c04fabcc-da97-47e1-bf42-883de1e14805",
    "event_id": "a0aab555-34e2-40fd-87ec-52ca98bea523",
    "seat_id": "seat-0001",
    "user_id": "user-001",
    "status": "reserved",
    "reserved_at": "2026-04-25T23:30:46.312002"
  }
}
```

> Guarda el `seat_id` usado en la variable `SEAT_ID` de Postman.

**Caso de error - Asiento ya reservado (409 Conflict):**

Si intentas reservar el mismo asiento otra vez:

```json
{
  "error": "El asiento ya está reservado"
}
```

---

### 6.4 Editar una Reserva (Cambiar de Asiento)

#### Opción A: Cambiar a otro asiento

| Campo   | Valor                                  |
| ------- | -------------------------------------- |
| Método  | `PUT`                                  |
| URL     | `{{BASE_URL}}/buyer/seats/{{SEAT_ID}}` |
| Headers | `Content-Type: application/json`       |

**Body (raw JSON):**

```json
{
  "event_id": "{{EVENT_ID}}",
  "user_id": "user-001",
  "new_seat_id": "seat-0003"
}
```

**Respuesta esperada (200 OK):**

```json
{
  "message": "Reserva actualizada exitosamente",
  "seat_id": "seat-0003",
  "event_id": "{{EVENT_ID}}",
  "updated_at": "2026-04-25T..."
}
```

> Después de esta operación, `seat-0001` queda `available` y `seat-0003` queda `reserved`.

---

### 6.5 Cancelar una Reserva

| Campo   | Valor                                                                       |
| ------- | --------------------------------------------------------------------------- |
| Método  | `DELETE`                                                                    |
| URL     | `{{BASE_URL}}/buyer/seats/seat-0003?event_id={{EVENT_ID}}&user_id=user-001` |
| Headers | Ninguno                                                                     |
| Body    | Ninguno                                                                     |

> Los parámetros `event_id` y `user_id` van como **query parameters** en la URL.

**Respuesta esperada (200 OK):**

```json
{
  "message": "Reserva cancelada exitosamente",
  "seat_id": "seat-0003",
  "event_id": "{{EVENT_ID}}",
  "cancelled_at": "2026-04-25T..."
}
```

> Después de cancelar, el asiento vuelve al estado `available` y los contadores se actualizan.

---

### 6.6 Confirmar Asistencia

> **Prerequisito:** Primero reserva un asiento nuevamente (repite paso 6.3 con `seat-0002` por ejemplo).

Luego confirmar asistencia:

| Campo   | Valor                            |
| ------- | -------------------------------- |
| Método  | `POST`                           |
| URL     | `{{BASE_URL}}/buyer/attendance`  |
| Headers | `Content-Type: application/json` |

**Body (raw JSON):**

```json
{
  "event_id": "{{EVENT_ID}}",
  "seat_id": "seat-0002",
  "user_id": "user-001"
}
```

**Respuesta esperada (200 OK):**

```json
{
  "message": "Asistencia confirmada exitosamente",
  "event_id": "{{EVENT_ID}}",
  "seat_id": "seat-0002",
  "user_id": "user-001",
  "attended_at": "2026-04-25T..."
}
```

> El estado del asiento cambia de `reserved` a `attended`.

**Caso de error - Sin reserva activa (403 Forbidden):**

```json
{
  "error": "No tienes una reserva activa para este asiento"
}
```

---

## 7. PARTE 3 - WebSocket (Estado de Asiento en Tiempo Real)

### Usando wscat (Terminal)

#### 7.1 Conectar al WebSocket

```bash
wscat -c "wss://yyyyyyyyyy.execute-api.us-east-1.amazonaws.com/dev?user_id=user-001&seat_id=seat-0001"
```

> Reemplaza la URL con tu `WebSocketUrl`. Los query parameters `user_id` y `seat_id` son opcionales en la conexión.

#### 7.2 Consultar Estado de un Asiento

Una vez conectado, envía el siguiente mensaje JSON:

```json
{
  "action": "getSeatStatus",
  "seat_id": "seat-0002",
  "event_id": "a0aab555-34e2-40fd-87ec-52ca98bea523"
}
```

**Respuesta esperada:**

```json
{
  "action": "seatStatus",
  "seat_id": "seat-0002",
  "event_id": "{{EVENT_ID}}",
  "status": "attended",
  "section": "general",
  "row": "1",
  "number": "2",
  "price": "50000",
  "reserved": true
}
```

#### 7.3 Consultar un Asiento Disponible

```json
{
  "action": "getSeatStatus",
  "seat_id": "seat-0005",
  "event_id": "{{EVENT_ID}}"
}
```

**Respuesta esperada:**

```json
{
  "action": "seatStatus",
  "seat_id": "seat-0005",
  "event_id": "{{EVENT_ID}}",
  "status": "available",
  "section": "general",
  "row": "1",
  "number": "5",
  "price": "50000"
}
```

#### 7.4 Consultar un Asiento Inexistente

```json
{
  "action": "getSeatStatus",
  "seat_id": "seat-9999",
  "event_id": "{{EVENT_ID}}"
}
```

**Respuesta esperada:**

```json
{
  "action": "seatStatus",
  "seat_id": "seat-9999",
  "event_id": "{{EVENT_ID}}",
  "status": "not_found",
  "message": "Asiento no encontrado"
}
```

#### 7.5 Desconectar

Presiona `Ctrl+C` para cerrar la conexión WebSocket.

### Usando Postman (WebSocket)

1. En Postman, crea una nueva **WebSocket Request**
2. URL: `wss://yyyyyyyyyy.execute-api.us-east-1.amazonaws.com/dev`
3. Haz clic en **Connect**
4. En el campo de mensaje, escribe:
   ```json
   {
     "action": "getSeatStatus",
     "seat_id": "seat-0001",
     "event_id": "{{EVENT_ID}}"
   }
   ```
5. Haz clic en **Send**
6. Verás la respuesta en el panel de mensajes

---

## 8. PARTE 4 - Eliminar un Evento

> **Nota:** Si el evento tiene reservas activas (status `reserved`), no se podrá eliminar. Primero cancela las reservas o confirma la asistencia de todos los asientos reservados.

| Campo   | Valor                                                             |
| ------- | ----------------------------------------------------------------- |
| Método  | `DELETE`                                                          |
| URL     | `{{BASE_URL}}/organizer/events/{{EVENT_ID}}?organizer_id=org-001` |
| Headers | Ninguno                                                           |
| Body    | Ninguno                                                           |

**Respuesta esperada (200 OK):**

```json
{
  "message": "Evento eliminado exitosamente",
  "event_id": "{{EVENT_ID}}"
}
```

**Caso de error - Tiene reservas activas (409 Conflict):**

```json
{
  "error": "No se puede eliminar el evento porque tiene reservas activas",
  "active_reservations": 1
}
```

> La eliminación es un **soft delete**: cambia el status a `deleted` en Aurora y limpia los asientos y contadores de DynamoDB.

---

## 9. Flujo de Prueba Completo Sugerido

Sigue este orden para probar toda la funcionalidad de extremo a extremo:

### Fase 1: Organizador crea y configura un evento

| Paso | Acción                              | Endpoint                                               | Método |
| ---- | ----------------------------------- | ------------------------------------------------------ | ------ |
| 1    | Crear evento (10 asientos)          | `POST /organizer/events`                               | POST   |
| 2    | Listar eventos del organizador      | `GET /organizer/events?organizer_id=org-001`           | GET    |
| 3    | Ver detalle del evento con asientos | `GET /organizer/events/{eventId}?organizer_id=org-001` | GET    |
| 4    | Editar nombre/descripción           | `PUT /organizer/events/{eventId}`                      | PUT    |
| 5    | Crear una alerta/campaña            | `POST /organizer/alerts`                               | POST   |
| 6    | Generar reporte del evento          | `POST /organizer/reports`                              | POST   |

### Fase 2: Comprador interactúa con el evento

| Paso | Acción                                           | Endpoint                                                 | Método |
| ---- | ------------------------------------------------ | -------------------------------------------------------- | ------ |
| 7    | Ver todos los eventos disponibles                | `GET /buyer/events`                                      | GET    |
| 8    | Ver detalle del evento y asientos                | `GET /buyer/events/{eventId}`                            | GET    |
| 9    | Reservar seat-0001                               | `POST /buyer/seats`                                      | POST   |
| 10   | Reservar seat-0002 (otro asiento)                | `POST /buyer/seats`                                      | POST   |
| 11   | Intentar reservar seat-0001 de nuevo (error 409) | `POST /buyer/seats`                                      | POST   |
| 12   | Cambiar de seat-0001 a seat-0005                 | `PUT /buyer/seats/seat-0001`                             | PUT    |
| 13   | Cancelar reserva de seat-0005                    | `DELETE /buyer/seats/seat-0005?event_id=...&user_id=...` | DELETE |
| 14   | Confirmar asistencia con seat-0002               | `POST /buyer/attendance`                                 | POST   |

### Fase 3: WebSocket en tiempo real

| Paso | Acción                          | Detalle                         |
| ---- | ------------------------------- | ------------------------------- |
| 15   | Conectar al WebSocket           | `wscat -c "wss://..."`          |
| 16   | Consultar seat-0002 (attended)  | Enviar JSON con `getSeatStatus` |
| 17   | Consultar seat-0005 (available) | Enviar JSON con `getSeatStatus` |
| 18   | Desconectar                     | `Ctrl+C`                        |

### Fase 4: Verificación final del organizador

| Paso | Acción                                 | Endpoint                                                  | Método |
| ---- | -------------------------------------- | --------------------------------------------------------- | ------ |
| 19   | Ver estadísticas del evento (asientos) | `GET /organizer/events/{eventId}?organizer_id=org-001`    | GET    |
| 20   | (Opcional) Eliminar el evento          | `DELETE /organizer/events/{eventId}?organizer_id=org-001` | DELETE |

---

### Resumen de Endpoints

| #   | Lambda                   | Método   | Ruta                            | Params / Body                                                                          |
| --- | ------------------------ | -------- | ------------------------------- | -------------------------------------------------------------------------------------- |
| 1   | org-create-event         | `POST`   | `/organizer/events`             | Body: `organizer_id`, `name`, `event_date`, `event_time`, `total_seats`, `location_id` |
| 2   | org-get-all-events       | `GET`    | `/organizer/events`             | Query: `organizer_id`                                                                  |
| 3   | org-get-event-seats      | `GET`    | `/organizer/events/{eventId}`   | Query: `organizer_id`                                                                  |
| 4   | org-edit-event           | `PUT`    | `/organizer/events/{eventId}`   | Body: `organizer_id`, + campos a editar                                                |
| 5   | org-delete-event         | `DELETE` | `/organizer/events/{eventId}`   | Query: `organizer_id`                                                                  |
| 6   | org-generate-report      | `POST`   | `/organizer/reports`            | Body: `event_id`, `organizer_id`, `report_type?`                                       |
| 7   | org-create-alert         | `POST`   | `/organizer/alerts`             | Body: `organizer_id`, `event_id`, `title`, `message`                                   |
| 8   | buyer-get-all-events     | `GET`    | `/buyer/events`                 | —                                                                                      |
| 9   | buyer-get-event-seats    | `GET`    | `/buyer/events/{eventId}`       | —                                                                                      |
| 10  | buyer-reserve-seat       | `POST`   | `/buyer/seats`                  | Body: `event_id`, `seat_id`, `user_id`                                                 |
| 11  | buyer-edit-reservation   | `PUT`    | `/buyer/seats/{seatId}`         | Body: `event_id`, `user_id`, `new_seat_id?`, `notes?`                                  |
| 12  | buyer-cancel-reservation | `DELETE` | `/buyer/seats/{seatId}`         | Query: `event_id`, `user_id`                                                           |
| 13  | buyer-confirm-attendance | `POST`   | `/buyer/attendance`             | Body: `event_id`, `seat_id`, `user_id`                                                 |
| 14  | ws-seat-status           | WS       | `$connect/$disconnect/$default` | Mensaje: `action`, `seat_id`, `event_id`                                               |
