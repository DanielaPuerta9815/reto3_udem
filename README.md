# Reto 3 - Sistema de Gestión de Eventos (AWS Serverless)

Sistema serverless de gestión y reserva de asientos para eventos, desplegado completamente en AWS mediante **Infrastructure as Code (IaC)** con CloudFormation y CI/CD con CodePipeline.

---

## Tabla de Contenidos

1. [Descripción General](#1-descripción-general)
2. [Arquitectura del Proyecto](#2-arquitectura-del-proyecto)
3. [Prerrequisitos](#3-prerrequisitos)
4. [Paso 1 - Crear una Cuenta de AWS](#paso-1---crear-una-cuenta-de-aws)
5. [Paso 2 - Crear un Usuario IAM con Permisos](#paso-2---crear-un-usuario-iam-con-permisos)
6. [Paso 3 - Instalar y Configurar AWS CLI](#paso-3---instalar-y-configurar-aws-cli)
7. [Paso 4 - Instalar Git](#paso-4---instalar-git)
8. [Paso 5 - Clonar el Repositorio](#paso-5---clonar-el-repositorio)
9. [Paso 6 - Configurar el Correo Electrónico para Notificaciones (SES)](#paso-6---configurar-el-correo-electrónico-para-notificaciones-ses)
10. [Paso 7 - Crear tu Propio Repositorio en GitHub](#paso-7---crear-tu-propio-repositorio-en-github)
11. [Paso 8 - Desplegar el Stack del Pipeline (CloudFormation)](#paso-8---desplegar-el-stack-del-pipeline-cloudformation)
12. [Paso 9 - Aprobar la Conexión a GitHub](#paso-9---aprobar-la-conexión-a-github)
13. [Paso 10 - Ejecutar el Pipeline y Esperar el Despliegue Completo](#paso-10---ejecutar-el-pipeline-y-esperar-el-despliegue-completo)
14. [Paso 11 - Verificar la Identidad de Correo en SES](#paso-11---verificar-la-identidad-de-correo-en-ses)
15. [Paso 12 - Obtener las URLs de las APIs](#paso-12---obtener-las-urls-de-las-apis)
16. [Paso 13 - Instalar Postman](#paso-13---instalar-postman)
17. [Paso 14 - Importar la Colección de Postman](#paso-14---importar-la-colección-de-postman)
18. [Paso 15 - Configurar Variables de Postman](#paso-15---configurar-variables-de-postman)
19. [Paso 16 - Registrar Usuarios (Auth)](#paso-16---registrar-usuarios-auth)
20. [Paso 17 - Iniciar Sesión y Obtener Token JWT](#paso-17---iniciar-sesión-y-obtener-token-jwt)
21. [Paso 18 - Probar los Endpoints del Organizador](#paso-18---probar-los-endpoints-del-organizador)
22. [Paso 19 - Probar los Endpoints del Comprador](#paso-19---probar-los-endpoints-del-comprador)
23. [Paso 20 - Probar el WebSocket (Opcional)](#paso-20---probar-el-websocket-opcional)
24. [Limpieza de Recursos (Importante)](#limpieza-de-recursos-importante)
25. [Solución de Problemas Comunes](#solución-de-problemas-comunes)
26. [Estructura del Proyecto](#estructura-del-proyecto)

---

## 1. Descripción General

Este proyecto implementa un sistema completo de gestión de eventos con las siguientes funcionalidades:

- **Organizadores**: crear, editar, eliminar eventos; ver asientos; generar reportes; crear alertas/notificaciones.
- **Compradores (Buyers)**: ver eventos disponibles; reservar asientos; cambiar asiento; cancelar reserva; confirmar asistencia.
- **Autenticación**: registro e inicio de sesión con Amazon Cognito (JWT).
- **Notificaciones**: envío de correos electrónicos vía Amazon SES y SNS.
- **Tiempo Real**: WebSocket para ver el estado de asientos en vivo.
- **Reportes**: generación asíncrona de reportes mediante EventBridge + SQS.
- **Recordatorios**: envío automático de recordatorios cada hora mediante EventBridge Scheduler.

---

## 2. Arquitectura del Proyecto

El despliegue se realiza mediante **un único stack de CloudFormation** (`00-pipeline.stack.yml`) que crea un **AWS CodePipeline**. Este pipeline se encarga automáticamente de desplegar los demás stacks en el siguiente orden:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS CodePipeline                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Stage 1: SOURCE ──> Descarga código desde GitHub                      │
│                                                                         │
│  Stage 2: BUILD ──> Empaqueta cada Lambda en un .zip (CodeBuild)       │
│                                                                         │
│  Stage 3: DEPLOY FOUNDATION (en paralelo):                             │
│     ├── 01-database.stack.yml     (DynamoDB + Aurora Serverless v2)     │
│     ├── 02-integration.stack.yml  (EventBridge, SQS, SNS, SES, S3)     │
│     ├── 03-cognito.stack.yml      (Cognito User Pool + Grupos)         │
│     └── 04-artifacts-stack.yml    (S3 bucket para código Lambda)       │
│                                                                         │
│  Stage 4: UPLOAD ──> Sube los .zip de Lambda al bucket S3 (CodeBuild)  │
│                                                                         │
│  Stage 5: DEPLOY LOGIC ──>                                             │
│     └── 05-logic.stack.yml  (18 Lambdas + HTTP API + WebSocket API)    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Servicios AWS utilizados:**

| Servicio                     | Uso                                                                     |
| ---------------------------- | ----------------------------------------------------------------------- |
| CloudFormation               | Infraestructura como código (IaC)                                       |
| CodePipeline                 | CI/CD - Orquestación del despliegue                                     |
| CodeBuild                    | Empaquetado y subida de Lambdas                                         |
| CodeStar Connections         | Conexión a GitHub                                                       |
| Lambda (Python 3.12)         | Lógica de negocio (18 funciones)                                        |
| API Gateway v2 (HTTP)        | API REST para buyers y organizers                                       |
| API Gateway v2 (WebSocket)   | Estado de asientos en tiempo real                                       |
| DynamoDB                     | Tablas de eventos, asientos y conexiones WebSocket                      |
| Aurora Serverless v2 (MySQL) | Base de datos relacional (organizadores, ubicaciones, eventos, alertas) |
| Cognito                      | Autenticación y autorización (JWT)                                      |
| EventBridge                  | Bus de eventos y programación de tareas                                 |
| SQS                          | Cola de procesamiento de reportes                                       |
| SNS                          | Notificaciones push                                                     |
| SES                          | Envío de correos electrónicos                                           |
| S3                           | Almacenamiento de código Lambda y reportes                              |
| Secrets Manager              | Credenciales de Aurora                                                  |
| CloudWatch Logs              | Logs de todas las Lambdas                                               |
| IAM                          | Roles y permisos                                                        |

---

## 3. Prerrequisitos

Antes de comenzar, necesitarás:

- Un **computador** con Windows, macOS o Linux
- Conexión a **Internet**
- Una **tarjeta de crédito o débito** (para crear la cuenta de AWS - el proyecto utiliza servicios dentro de la capa gratuita en su mayoría, pero algunos servicios como Aurora Serverless v2 pueden generar costos)
- Una **cuenta de correo electrónico** activa (Gmail, Outlook, etc.)
- Una **cuenta de GitHub** (gratuita)

> ⚠️ **IMPORTANTE SOBRE COSTOS**: Este proyecto utiliza Aurora Serverless v2 que tiene un costo por hora de uso. **Asegúrate de eliminar todos los recursos al finalizar las pruebas** (ver sección de [Limpieza de Recursos](#limpieza-de-recursos-importante)).

---

## Paso 1 - Crear una Cuenta de AWS

Si ya tienes una cuenta de AWS, pasa al [Paso 2](#paso-2---crear-un-usuario-iam-con-permisos).

1. Abre tu navegador y ve a: **https://aws.amazon.com/**
2. Haz clic en **"Crear una cuenta de AWS"** (esquina superior derecha)
3. Ingresa tu **correo electrónico** y un **nombre para la cuenta**
4. Haz clic en **"Verificar dirección de correo electrónico"**
5. Revisa tu correo y escribe el **código de verificación**
6. Crea una **contraseña** segura
7. Selecciona **"Personal"** como tipo de cuenta
8. Llena tus **datos personales** (nombre, teléfono, dirección)
9. Ingresa los **datos de tu tarjeta de crédito/débito** (se hace un cargo temporal de $1 USD que se devuelve)
10. Verifica tu identidad por **teléfono** (recibirás un SMS o llamada)
11. Selecciona el plan **"Basic Support - Gratuito"**
12. Haz clic en **"Completar registro"**
13. Espera unos minutos y luego inicia sesión en: **https://console.aws.amazon.com/**

---

## Paso 2 - Crear un Usuario IAM con Permisos

Por seguridad, no usaremos el usuario root. Crearemos un usuario IAM con permisos administrativos.

1. Inicia sesión en la consola de AWS: **https://console.aws.amazon.com/**
2. En la barra de búsqueda superior, escribe **IAM** y haz clic en el servicio **"IAM"**
3. En el menú izquierdo, haz clic en **"Users"** (Usuarios)
4. Haz clic en **"Create user"** (Crear usuario)
5. Escribe un nombre de usuario, por ejemplo: `reto3-admin`
6. Marca la casilla **"Provide user access to the AWS Management Console"**
7. Selecciona **"I want to create an IAM user"**
8. Selecciona **"Custom password"** y escribe una contraseña segura
9. Desmarca **"Users must create a new password at next sign-in"**
10. Haz clic en **"Next"** (Siguiente)
11. Selecciona **"Attach policies directly"** (Adjuntar políticas directamente)
12. Busca y selecciona la política: **`AdministratorAccess`**
13. Haz clic en **"Next"** y luego **"Create user"**
14. **IMPORTANTE**: En la pantalla de confirmación, copia y guarda:
    - El **URL de inicio de sesión de la consola** (algo como `https://123456789012.signin.aws.amazon.com/console`)
    - El **nombre de usuario**
    - La **contraseña**
15. Haz clic en **"Return to users list"**

### Crear Access Keys para el CLI

1. En la lista de usuarios, haz clic en el usuario que acabas de crear (`reto3-admin`)
2. Ve a la pestaña **"Security credentials"** (Credenciales de seguridad)
3. Baja hasta la sección **"Access keys"** y haz clic en **"Create access key"**
4. Selecciona **"Command Line Interface (CLI)"**
5. Marca la casilla de confirmación al final y haz clic en **"Next"**
6. (Opcional) Escribe una descripción como `CLI reto3`
7. Haz clic en **"Create access key"**
8. **IMPORTANTE**: Copia y guarda en un lugar seguro:
   - **Access Key ID** (algo como `AKIAIOSFODNN7EXAMPLE`)
   - **Secret Access Key** (algo como `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`)
9. **NO cierres esta ventana hasta haberlos copiado**. Después de cerrarla, no podrás ver el Secret Access Key de nuevo.
10. Haz clic en **"Done"**

---

## Paso 3 - Instalar y Configurar AWS CLI

### Instalación

#### Windows

1. Descarga el instalador de AWS CLI v2 desde: **https://awscli.amazonaws.com/AWSCLIV2.msi**
2. Ejecuta el archivo `.msi` descargado
3. Sigue el asistente de instalación (Next → Next → Install → Finish)
4. **Cierra y vuelve a abrir** cualquier ventana de terminal/PowerShell/CMD que tengas abierta

#### macOS

Abre la **Terminal** y ejecuta:

```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
```

#### Linux

Abre la **Terminal** y ejecuta:

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Verificar la instalación

Abre una terminal (CMD, PowerShell o Terminal) y ejecuta:

```bash
aws --version
```

Deberías ver algo como: `aws-cli/2.x.x Python/3.x.x ...`

### Configurar las credenciales

En la misma terminal, ejecuta:

```bash
aws configure
```

Se te pedirán 4 datos. Escríbelos uno por uno:

```
AWS Access Key ID [None]: PEGA_AQUI_TU_ACCESS_KEY_ID
AWS Secret Access Key [None]: PEGA_AQUI_TU_SECRET_ACCESS_KEY
Default region name [None]: us-east-1
Default output format [None]: json
```

> **IMPORTANTE**: Usa la región **`us-east-1`** (N. Virginia). Todo el proyecto se desplegará en esta región.

### Verificar la configuración

Ejecuta:

```bash
aws sts get-caller-identity
```

Deberías ver algo como:

```json
{
  "UserId": "AIDAEXAMPLE",
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/reto3-admin"
}
```

> **Anota tu número de cuenta** (el campo `Account`, por ejemplo `123456789012`). Lo necesitarás más adelante.

---

## Paso 4 - Instalar Git

### Windows

1. Descarga Git desde: **https://git-scm.com/download/win**
2. Ejecuta el instalador descargado
3. Acepta todas las opciones por defecto (Next → Next → ... → Install → Finish)
4. **Cierra y vuelve a abrir** la terminal

### macOS

Abre la Terminal y ejecuta:

```bash
xcode-select --install
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install git -y
```

### Verificar la instalación

```bash
git --version
```

Deberías ver algo como: `git version 2.x.x`

---

## Paso 5 - Clonar el Repositorio

1. Abre una terminal
2. Navega a la carpeta donde quieras guardar el proyecto. Por ejemplo:

   **Windows (PowerShell/CMD):**

   ```bash
   cd %USERPROFILE%\Documents
   ```

   **macOS/Linux:**

   ```bash
   cd ~/Documents
   ```

3. Clona el repositorio:

   ```bash
   git clone https://github.com/DanielaPuerta9815/reto3_udem.git
   ```

4. Entra a la carpeta del proyecto:

   ```bash
   cd reto3_udem
   ```

5. Verifica que los archivos están presentes:

   ```bash
   ls
   ```

   Deberías ver archivos como: `00-pipeline.stack.yml`, `01-database.stack.yml`, carpeta `codes/`, etc.

---

## Paso 6 - Configurar el Correo Electrónico para Notificaciones (SES)

El sistema envía notificaciones por correo electrónico usando Amazon SES. Necesitas configurar un correo electrónico real en el proyecto.

1. Abre el archivo `02-integration.stack.yml` con un editor de texto (Bloc de notas, VS Code, Notepad++, etc.)

2. Busca la sección de parámetros (cerca de la línea 21):

   ```yaml
   SesEmail:
     Type: String
     Description: >
       Correo electronico que se usara como identidad verificada en SES para enviar notificaciones.
   ```

3. **Agrega una línea `Default`** con tu correo electrónico real, para que quede así:

   ```yaml
   SesEmail:
     Type: String
     Default: "tu-correo-real@gmail.com"
     Description: >
       Correo electronico que se usara como identidad verificada en SES para enviar notificaciones.
   ```

   > **Reemplaza** `tu-correo-real@gmail.com` con tu dirección de correo electrónico real (Gmail, Outlook, etc.).

4. **Guarda el archivo**.

---

## Paso 7 - Crear tu Propio Repositorio en GitHub

El pipeline de CI/CD necesita conectarse a un repositorio de GitHub **tuyo** para poder leer el código fuente. Debes crear tu propio repositorio y subir el código.

### 7.1 - Crear cuenta de GitHub (si no tienes una)

1. Ve a **https://github.com**
2. Haz clic en **"Sign up"**
3. Sigue los pasos para crear tu cuenta (correo, contraseña, nombre de usuario)
4. Verifica tu correo electrónico

### 7.2 - Crear un nuevo repositorio

1. Inicia sesión en **https://github.com**
2. Haz clic en el botón **"+"** (esquina superior derecha) → **"New repository"**
3. Configura lo siguiente:
   - **Repository name**: `reto3_udem` (o el nombre que prefieras)
   - **Description** (opcional): `Reto 3 - Sistema de Gestión de Eventos AWS`
   - **Visibility**: **Public**
   - **NO** marques "Add a README file"
   - **NO** marques "Add .gitignore"
   - **NO** marques "Choose a license"
4. Haz clic en **"Create repository"**
5. **No cierres esta página**. Necesitarás la URL del repositorio que aparece (algo como `https://github.com/TU_USUARIO/reto3_udem.git`)

### 7.3 - Subir el código a tu repositorio

Abre una terminal y asegúrate de estar dentro de la carpeta del proyecto clonado:

```bash
cd reto3_udem
```

Ejecuta los siguientes comandos uno por uno:

```bash
git remote remove origin
```

```bash
git remote add origin https://github.com/TU_USUARIO_GITHUB/reto3_udem.git
```

> **Reemplaza** `TU_USUARIO_GITHUB` con tu nombre de usuario de GitHub.

```bash
git add .
```

```bash
git commit -m "Despliegue inicial Reto 3"
```

```bash
git branch -M main
```

```bash
git push -u origin main
```

> Si te pide autenticación, ingresa tu **nombre de usuario de GitHub** y como contraseña usa un **Personal Access Token** (no tu contraseña de GitHub). Para crear un token:
>
> 1. Ve a **https://github.com/settings/tokens**
> 2. Haz clic en **"Generate new token (classic)"**
> 3. Dale un nombre como `reto3-deploy`
> 4. Selecciona el scope: **`repo`** (todo el checkbox de repo)
> 5. Haz clic en **"Generate token"**
> 6. **Copia el token** y úsalo como contraseña cuando Git te lo pida

Verifica que el código se subió correctamente visitando tu repositorio en GitHub.

---

## Paso 8 - Desplegar el Stack del Pipeline (CloudFormation)

Este es el paso más importante. Al desplegar este stack, se creará **todo el pipeline de CI/CD** que a su vez desplegará automáticamente toda la infraestructura restante.

#### Prerrequisitos

  Antes de desplegar el stack, asegúrate de cumplir con lo siguiente:

  - Tener permisos para desplegar recursos con CloudFormation
  - Tener creado el **Service Linked Role de RDS**

  ---

  #### Crear el Service Linked Role (solo una vez por cuenta)

  Ejecuta el siguiente comando:

  ```bash
  aws iam create-service-linked-role --aws-service-name rds.amazonaws.com
  ```
### 8.1 - Ejecutar el comando de creación del stack

Abre una terminal y ejecuta el siguiente comando **completo** (es un solo comando, cópialo todo):

**Windows (CMD):**

```bash
aws cloudformation create-stack --stack-name reto3-dev-pipeline --template-body file://00-pipeline.stack.yml --parameters ParameterKey=GitHubOwner,ParameterValue=TU_USUARIO_GITHUB ParameterKey=GitHubRepo,ParameterValue=reto3_udem ParameterKey=GitHubBranch,ParameterValue=main ParameterKey=Stage,ParameterValue=dev --capabilities CAPABILITY_NAMED_IAM --region us-east-1
```

**macOS/Linux:**

```bash
aws cloudformation create-stack \
  --stack-name reto3-dev-pipeline \
  --template-body file://00-pipeline.stack.yml \
  --parameters \
    ParameterKey=GitHubOwner,ParameterValue=TU_USUARIO_GITHUB \
    ParameterKey=GitHubRepo,ParameterValue=reto3_udem \
    ParameterKey=GitHubBranch,ParameterValue=main \
    ParameterKey=Stage,ParameterValue=dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

> **IMPORTANTE**: Reemplaza `TU_USUARIO_GITHUB` con tu nombre de usuario de GitHub (ejemplo: `JuanPerez`).
> Si nombraste tu repositorio diferente a `reto3_udem`, cambia también `reto3_udem` por el nombre correcto.
> Valida la rama en la cual esta el código, por defecto queda en la rama "main" pero en caso de modificarla (por ejemplo por "master") reemplaza el Value=main del parametro GitHubBranch

### 8.2 - Verificar que se está creando

Deberías ver una respuesta como:

```json
{
  "StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/reto3-dev-pipeline/..."
}
```

Para ver el estado del stack:

```bash
aws cloudformation describe-stacks --stack-name reto3-dev-pipeline --query "Stacks[0].StackStatus" --region us-east-1
```

Espera hasta que el estado sea **`CREATE_COMPLETE`**. Esto puede tomar entre **3 y 5 minutos**.

Puedes ejecutar el comando anterior repetidamente hasta que veas `CREATE_COMPLETE`.

También puedes ver el progreso en la consola web:

1. Ve a **https://console.aws.amazon.com/cloudformation**
2. Asegúrate de estar en la región **N. Virginia (us-east-1)** (selector en la esquina superior derecha)
3. Busca el stack `reto3-dev-pipeline`
4. Haz clic en él para ver los eventos y el estado

> Si ves `CREATE_FAILED` o `ROLLBACK_COMPLETE`, ve a la sección de [Solución de Problemas](#solución-de-problemas-comunes).

---

## Paso 9 - Aprobar la Conexión a GitHub

Después de que el stack del pipeline se cree exitosamente, la conexión a GitHub queda en estado **PENDING** (pendiente). Debes aprobarla manualmente.

1. Ve a la consola de AWS: **https://console.aws.amazon.com/**
2. En la barra de búsqueda, escribe **"CodePipeline"** y haz clic en el servicio
3. En el menú izquierdo, haz clic en **"Settings"** → **"Connections"**

   > También puedes ir directamente a: `https://us-east-1.console.aws.amazon.com/codesuite/settings/connections?region=us-east-1`

4. Verás una conexión llamada **`reto3-dev-github-connection`** con estado **"Pending"**
5. Haz clic en el nombre de la conexión
6. Haz clic en **"Update pending connection"**
7. Se abrirá una ventana emergente para autorizar a AWS a acceder a tu cuenta de GitHub
8. Haz clic en **"Install a new app"** (si es la primera vez)
9. Selecciona tu cuenta de GitHub
10. Puedes elegir **"All repositories"** o seleccionar solo el repositorio `reto3_udem`
11. Haz clic en **"Install"**
12. Haz clic en **"Connect"**
13. El estado de la conexión debe cambiar a **"Available"** ✅

---

## Paso 10 - Ejecutar el Pipeline y Esperar el Despliegue Completo

### 10.1 - Liberar (Release) el pipeline

Una vez aprobada la conexión a GitHub, necesitas iniciar la ejecución del pipeline manualmente la primera vez:

1. Ve a **https://console.aws.amazon.com/codesuite/codepipeline/pipelines** (asegúrate de estar en la región `us-east-1`)
2. Haz clic en el pipeline **`reto3-dev-pipeline`**
3. Haz clic en el botón **"Release change"** (esquina superior derecha)
4. Confirma haciendo clic en **"Release"**

### 10.2 - Monitorear el progreso

El pipeline ejecutará los 5 stages en orden. Puedes ver el progreso en la misma página:

| Stage                | Descripción                                                                | Tiempo aproximado |
| -------------------- | -------------------------------------------------------------------------- | ----------------- |
| **Source**           | Descarga el código de GitHub                                               | ~1 minuto         |
| **Build**            | Empaqueta las Lambdas en archivos .zip                                     | ~2-3 minutos      |
| **DeployFoundation** | Despliega 4 stacks en paralelo (Database, Integration, Cognito, Artifacts) | ~10-15 minutos    |
| **UploadLambdas**    | Sube los .zip al bucket S3                                                 | ~2 minutos        |
| **DeployLogic**      | Despliega las 18 Lambdas + API Gateway + WebSocket                         | ~5-10 minutos     |

> **Tiempo total estimado: 20-30 minutos** (la mayor parte del tiempo lo toma la creación de Aurora Serverless v2 en el stage DeployFoundation).

Espera hasta que **TODOS los stages** estén en verde (**Succeeded**) ✅.

> Si algún stage falla, haz clic en el enlace **"Details"** del stage fallido para ver los logs de error. Consulta la sección de [Solución de Problemas](#solución-de-problemas-comunes).

---

## Paso 11 - Verificar la Identidad de Correo en SES

Durante el despliegue, AWS envió un correo de verificación a la dirección que configuraste en el [Paso 6](#paso-6---configurar-el-correo-electrónico-para-notificaciones-ses).

1. Abre tu **bandeja de entrada** del correo que configuraste
2. Busca un correo de **"Amazon Web Services"** con asunto **"Amazon SES - Email Address Verification Request"** o similar
3. Haz clic en el **enlace de verificación** dentro del correo
4. Deberías ver una página de confirmación de AWS

> Sin este paso, el sistema no podrá enviar correos de notificación.

> **NOTA**: Si estás en SES **Sandbox mode** (modo de pruebas, que es el modo por defecto para cuentas nuevas), solo puedes enviar correos a direcciones verificadas. Para pruebas es suficiente.

---

## Paso 12 - Obtener las URLs de las APIs

Una vez que el pipeline haya finalizado exitosamente, necesitas obtener las URLs de las APIs desplegadas.

### Opción A - Desde la terminal (recomendado)

Ejecuta:

```bash
aws cloudformation describe-stacks --stack-name reto3-dev-logic --query "Stacks[0].Outputs" --region us-east-1 --output table
```

Busca los valores de:

- **`HttpApiUrl`**: URL base del API REST (algo como `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev`)
- **`WebSocketUrl`**: URL del WebSocket (algo como `wss://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev`)

### Opción B - Desde la consola web

1. Ve a **https://console.aws.amazon.com/cloudformation** (región `us-east-1`)
2. Haz clic en el stack **`reto3-dev-logic`**
3. Ve a la pestaña **"Outputs"**
4. Busca `HttpApiUrl` y `WebSocketUrl`

> **Copia y guarda estas URLs**. Las necesitarás en los siguientes pasos.

---

## Paso 13 - Instalar Postman

1. Ve a **https://www.postman.com/downloads/**
2. Descarga la versión para tu sistema operativo
3. Instala y abre Postman
4. Puedes crear una cuenta gratuita o hacer clic en **"Skip and go to the app"** para usar sin cuenta

---

## Paso 14 - Importar la Colección de Postman

1. Abre Postman
2. Haz clic en **"Import"** (esquina superior izquierda)
3. Haz clic en **"Upload Files"**
4. Navega hasta la carpeta del proyecto y selecciona el archivo:
   ```
   Postman_Test_Apis/Reto3_UdeM_AWS.postman_collection.json
   ```
5. Haz clic en **"Import"**
6. Deberías ver la colección **"Reto3_UdeM_AWS"** en el panel izquierdo con todos los endpoints

---

## Paso 15 - Configurar Variables de Postman

### 15.1 - Crear un Environment

1. En Postman, haz clic en **"Environments"** (panel izquierdo) o en el ícono de engranaje
2. Haz clic en **"Create Environment"** (o el botón **"+"**)
3. Nómbralo: `Reto3 AWS Dev`
4. Agrega las siguientes variables:

| Variable   | Type    | Initial Value                                                |
| ---------- | ------- | ------------------------------------------------------------ |
| `BASE_URL` | default | `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev` |
| `EVENT_ID` | default | (dejar vacío - se llenará después)                           |
| `SEAT_ID`  | default | (dejar vacío - se llenará después)                           |
| `TOKEN`    | default | (dejar vacío - se llenará después)                           |

> **IMPORTANTE**: En `BASE_URL`, pega la URL de `HttpApiUrl` que obtuviste en el [Paso 12](#paso-12---obtener-las-urls-de-las-apis). **NO** agregues `/` al final.

5. Haz clic en **"Save"**
6. Selecciona el environment **"Reto3 AWS Dev"** en el dropdown de la esquina superior derecha de Postman

### 15.2 - Configurar el Authorization Header

Para los endpoints que requieren autenticación (todos excepto `/auth/signup` y `/auth/login`), necesitas configurar el header de autorización:

1. Haz clic en la colección **"Reto3_UdeM_AWS"**
2. Ve a la pestaña **"Authorization"** (o "Auth")
3. Selecciona Type: **"Bearer Token"**
4. En el campo Token, escribe: `{{TOKEN}}`
5. Haz clic en **"Save"**

> Esto aplicará automáticamente el token JWT a todas las peticiones de la colección.

---

## Paso 16 - Registrar Usuarios (Auth)

Primero necesitas registrar usuarios en Cognito para poder autenticarte.

### 16.1 - Obtener el User Pool ID y Client ID

Ejecuta en la terminal:

```bash
aws cloudformation describe-stacks --stack-name reto3-dev-cognito --query "Stacks[0].Outputs" --region us-east-1 --output table
```

Anota los valores de:

- **`UserPoolId`** (algo como `us-east-1_XXXXXXXXX`)
- **`UserPoolClientId`** (algo como `1abc2defgh3ijklmnop4qrst5u`)

### 16.2 - Registrar un Organizador

En Postman, crea una nueva petición (o usa el endpoint de Auth) con:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/auth/signup`
- **Headers**: `Content-Type: application/json`
- **Body** (raw, JSON):

```json
{
  "email": "organizador@tudominio.com",
  "password": "Password123!",
  "name": "Juan Organizador",
  "group": "ORGANIZER"
}
```

> **IMPORTANTE sobre la contraseña**: Debe tener mínimo 8 caracteres, incluir mayúsculas, minúsculas, números y al menos un carácter especial (`!@#$%^&*`).

Haz clic en **"Send"**. Deberías recibir una respuesta exitosa (status `200`).

### 16.3 - Registrar un Comprador (Buyer)

Crea otra petición similar:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/auth/signup`
- **Body** (raw, JSON):

```json
{
  "email": "comprador@tudominio.com",
  "password": "Password123!",
  "name": "María Compradora",
  "group": "ATTENDEE"
}
```

Haz clic en **"Send"**.

### 16.4 - Confirmar la Suscripción a Notificaciones (SNS)

Al registrar cada usuario, el sistema lo suscribe automáticamente al tópico de notificaciones de **Amazon SNS**. Para que el usuario reciba correos de notificación (alertas, confirmaciones de reserva, actualizaciones de eventos, etc.), debe **confirmar la suscripción**:

1. Abre la **bandeja de entrada** del correo que usaste para registrar al usuario (tanto el organizador como el comprador)
2. Busca un correo de **"AWS Notifications"** con asunto **"AWS Notification - Subscription Confirmation"**
3. Haz clic en el enlace **"Confirm subscription"** dentro del correo
4. Deberías ver una página de AWS confirmando la suscripción: **"Subscription confirmed!"** ✅

> **IMPORTANTE**: Repite este paso para **cada usuario registrado** (organizador y comprador). Si no se confirma la suscripción, ese usuario no recibirá las notificaciones por correo.

> **NOTA**: Si no ves el correo, revisa la carpeta de **spam/correo no deseado**. Los correos de confirmación de SNS a veces pueden llegar ahí.

---

## Paso 17 - Iniciar Sesión y Obtener Token JWT

### 17.1 - Login como Organizador

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/auth/login`
- **Headers**: `Content-Type: application/json`
- **Body** (raw, JSON):

```json
{
  "email": "organizador@tudominio.com",
  "password": "Password123!"
}
```

Haz clic en **"Send"**.

La respuesta incluirá un campo `IdToken` (o `token`). **Copia todo el valor del token**.

### 17.2 - Guardar el Token en la Variable de Postman

1. En Postman, ve a **"Environments"** → **"Reto3 AWS Dev"**"
2. En la variable `TOKEN`, pega el token JWT que copiaste (propiedad "id_token")
3. Haz clic en **"Save"**

> Ahora todas las peticiones que usen `{{TOKEN}}` incluirán automáticamente el header `Authorization: Bearer <token>`.

> **NOTA**: Los tokens JWT expiran después de un tiempo (generalmente 1 hora). Si un endpoint devuelve un error `401 Unauthorized`, repite el login para obtener un nuevo token.

---

## Paso 18 - Probar los Endpoints del Organizador

Asegúrate de tener el token del **Organizador** configurado en la variable `TOKEN`.

### 18.1 - Crear un Evento

Usa el request **"Organizer - CREATE EVENT"** de la colección:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/organizer/events`
- **Body**:

```json
{
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

Haz clic en **"Send"**. La respuesta incluirá un `event_id`.

> **Copia el `event_id`** de la respuesta y guárdalo en la variable de Postman `EVENT_ID`.

### 18.2 - Ver Mis Eventos

Usa **"Organizer - GET MY EVENTS"**:

- **Método**: `GET`
- **URL**: `{{BASE_URL}}/organizer/events`

### 18.3 - Ver Asientos de un Evento

Usa **"Organizer - GET SEATS BY EVENT"**:

- **Método**: `GET`
- **URL**: `{{BASE_URL}}/organizer/events/{{EVENT_ID}}`

### 18.4 - Actualizar un Evento

Usa **"Organizer - UPDATE EVENT"**:

- **Método**: `PUT`
- **URL**: `{{BASE_URL}}/organizer/events/{{EVENT_ID}}`
- **Body**:

```json
{
  "name": "Concierto de Rock 2026 - Edición Especial",
  "description": "Evento actualizado con artistas sorpresa"
}
```

### 18.5 - Crear una Alerta/Notificación

Usa **"Organizer - CREATE ALERT/NOTIFICATION"**:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/organizer/alerts`
- **Body**:

```json
{
  "event_id": "{{EVENT_ID}}",
  "title": "¡Últimas entradas disponibles!",
  "message": "No te pierdas el Concierto de Rock 2026. Quedan pocas entradas.",
  "alert_type": "promotion",
  "target_audience": "all"
}
```

### 18.6 - Generar un Reporte

Se tienen los siguientes reportes disponibles 

- general: Información general del evento
- attendance: Asistentes del evento
- sales: Ventas que ha tenido el evento
- occupancy: Ocupación del evento 

Según el reporte del cual se desee obtener la información, se debe configurar en el valor `report_type`

Usa **"Organizer - CREATE REPORT"**:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/organizer/reports`
- **Body**:

```json
{
  "event_id": "{{EVENT_ID}}",
  "report_type": "general"
}
```

> El reporte se genera de forma asíncrona: la solicitud se envía a EventBridge, luego a SQS, y finalmente una Lambda lo procesa y lo guarda en S3.

---

## Paso 19 - Probar los Endpoints del Comprador

Debes hacer login con el usuario comprador y actualizar la variable `TOKEN`.

### 19.1 - Ver Todos los Eventos

Usa **"Buyer - GET ALL EVENTS"**:

- **Método**: `GET`
- **URL**: `{{BASE_URL}}/buyer/events`

### 19.2 - Ver Asientos de un Evento

Usa **"Buyer - GET SEATS BY EVENT"**:

- **Método**: `GET`
- **URL**: `{{BASE_URL}}/buyer/events/{{EVENT_ID}}`

### 19.3 - Reservar un Asiento

Usa **"Buyer - BUY SEAT"**:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/buyer/seats`
- **Body**:

```json
{
  "event_id": "{{EVENT_ID}}",
  "seat_id": "seat-0001"
}
```

> El `user_id` se obtiene automáticamente del token JWT, no es necesario enviarlo.

Guarda el `seat_id` en la variable `SEAT_ID` si la respuesta devuelve uno diferente.

### 19.4 - Cambiar de Asiento

Usa **"Buyer - CHANGE SEAT"**:

- **Método**: `PUT`
- **URL**: `{{BASE_URL}}/buyer/seats/{{SEAT_ID}}`
- **Body**:

```json
{
  "event_id": "{{EVENT_ID}}",
  "new_seat_id": "seat-0003"
}
```

### 19.5 - Confirmar Asistencia

Usa **"Buyer - ATTENDANCE"**:

- **Método**: `POST`
- **URL**: `{{BASE_URL}}/buyer/attendance`
- **Body**:

```json
{
  "event_id": "{{EVENT_ID}}",
  "seat_id": "seat-0001"
}
```

### 19.6 - Cancelar Reserva

Usa **"Buyer - CANCEL SEAT"**:

- **Método**: `DELETE`
- **URL**: `{{BASE_URL}}/buyer/seats/{{SEAT_ID}}?event_id={{EVENT_ID}}`

---

## Paso 20 - Probar el WebSocket (Opcional)

El proyecto incluye un WebSocket API para ver el estado de asientos en tiempo real.

### Usando wscat (terminal)

1. Instala wscat (requiere Node.js):

   ```bash
   npm install -g wscat
   ```

2. Conéctate al WebSocket:

   ```bash
   wscat -c "wss://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev"
   ```

   > Reemplaza la URL con el `WebSocketUrl` del [Paso 12](#paso-12---obtener-las-urls-de-las-apis).

3. Una vez conectado, envía un mensaje para suscribirte a un evento:

   ```json
   { "action": "subscribe", "event_id": "TU_EVENT_ID_AQUI" }
   ```

4. Desde otra terminal o Postman, haz una reserva de asiento. Deberías ver una actualización en la terminal del WebSocket.

### Usando Postman

1. En Postman, crea una nueva petición de tipo **"WebSocket"**
2. Pega la URL del WebSocket: `wss://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev`
3. Haz clic en **"Connect"**
4. En el campo de mensaje, escribe:
   ```json
   { "action": "subscribe", "event_id": "TU_EVENT_ID" }
   ```
5. Haz clic en **"Send"**

---

## Limpieza de Recursos (Importante)

> ⚠️ **MUY IMPORTANTE**: Para evitar cargos innecesarios en tu cuenta de AWS, debes eliminar todos los recursos cuando termines las pruebas.

### Orden de eliminación

Los stacks deben eliminarse en orden **inverso** al de creación, empezando por los que tienen dependencias:

#### 1. Eliminar el stack de Logic

```bash
aws cloudformation delete-stack --stack-name reto3-dev-logic --region us-east-1
```

Espera a que se complete:

```bash
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-logic --region us-east-1
```

#### 2. Eliminar los stacks de Foundation

```bash
aws cloudformation delete-stack --stack-name reto3-dev-artifacts --region us-east-1
```

```bash
aws cloudformation delete-stack --stack-name reto3-dev-cognito --region us-east-1
```

```bash
aws cloudformation delete-stack --stack-name reto3-dev-integration --region us-east-1
```

```bash
aws cloudformation delete-stack --stack-name reto3-dev-database --region us-east-1
```

Espera a que todos se completen:

```bash
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-artifacts --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-cognito --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-integration --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-database --region us-east-1
```

> **NOTA**: Si el stack `reto3-dev-artifacts` falla al eliminarse porque el bucket S3 no está vacío, primero vacía el bucket:
>
> ```bash
> aws s3 rm s3://reto3-dev-lambda-code-TU_ACCOUNT_ID --recursive --region us-east-1
> ```
>
> Luego reintenta la eliminación del stack.

> **NOTA**: Si el stack `reto3-dev-integration` falla porque el bucket de reportes no está vacío:
>
> ```bash
> aws s3 rm s3://reto3-dev-reports --recursive --region us-east-1
> ```
>
> Luego reintenta la eliminación del stack.

#### 3. Eliminar el stack del Pipeline

Primero, vacía el bucket de artefactos del pipeline:

```bash
aws s3 rm s3://reto3-dev-pipeline-artifacts-TU_ACCOUNT_ID --recursive --region us-east-1
```

> Reemplaza `TU_ACCOUNT_ID` con tu número de cuenta de AWS (el que anotaste en el [Paso 3](#paso-3---instalar-y-configurar-aws-cli)).

Luego elimina el stack:

```bash
aws cloudformation delete-stack --stack-name reto3-dev-pipeline --region us-east-1
```

```bash
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-pipeline --region us-east-1
```

#### 4. Verificar que no quedan recursos

```bash
aws cloudformation list-stacks --query "StackSummaries[?contains(StackName, 'reto3') && StackStatus != 'DELETE_COMPLETE']" --region us-east-1 --output table
```

Si la tabla está vacía o no aparecen stacks, todos los recursos han sido eliminados correctamente ✅.

---

## Solución de Problemas Comunes

### El stack del pipeline falla con `CREATE_FAILED`

**Causa posible**: Ya existe un recurso con el mismo nombre (de un despliegue anterior incompleto).

**Solución**:

```bash
aws cloudformation delete-stack --stack-name reto3-dev-pipeline --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name reto3-dev-pipeline --region us-east-1
```

Luego intenta crear el stack de nuevo.

---

### El stage DeployFoundation falla en DeployIntegration

**Causa posible**: El parámetro `SesEmail` no tiene un valor configurado.

**Solución**: Verifica que editaste el archivo `02-integration.stack.yml` y agregaste la línea `Default: "tu-correo@ejemplo.com"` al parámetro `SesEmail` (ver [Paso 6](#paso-6---configurar-el-correo-electrónico-para-notificaciones-ses)). Después de editar:

```bash
git add .
git commit -m "Configurar SES email"
git push
```

El pipeline se ejecutará automáticamente al detectar el cambio en GitHub.

---

### Los endpoints devuelven `401 Unauthorized`

**Causa**: El token JWT ha expirado o no se está enviando correctamente.

**Solución**:

1. Haz login nuevamente para obtener un nuevo token (ver [Paso 17](#paso-17---iniciar-sesión-y-obtener-token-jwt))
2. Actualiza la variable `TOKEN` en el Environment de Postman
3. Verifica que en la pestaña "Authorization" de la petición está configurado `Bearer Token` con valor `{{TOKEN}}`

---

### Los endpoints devuelven `403 Forbidden`

**Causa**: El usuario no tiene el rol correcto para acceder al endpoint.

**Solución**: Asegúrate de estar usando el token del usuario con el rol adecuado:

- Endpoints `/organizer/*` → requieren token de usuario con rol `ORGANIZER`
- Endpoints `/buyer/*` → requieren token de usuario con rol `ATTENDEE`

---

### El pipeline se queda en estado "InProgress" en el stage Source

**Causa**: La conexión a GitHub no ha sido aprobada.

**Solución**: Completa el [Paso 9](#paso-9---aprobar-la-conexión-a-github) para aprobar la conexión.

---

### Error al eliminar stacks: "bucket is not empty"

**Causa**: Los buckets S3 tienen contenido y CloudFormation no puede eliminarlos.

**Solución**: Vacía los buckets antes de eliminar los stacks:

```bash
# Ver tus buckets de reto3
aws s3 ls | grep reto3

# Vaciar cada bucket
aws s3 rm s3://NOMBRE_DEL_BUCKET --recursive
```

---

### No llegan correos de notificación

**Causas posibles**:

1. No verificaste el correo en SES (ver [Paso 11](#paso-11---verificar-la-identidad-de-correo-en-ses))
2. La cuenta está en SES Sandbox mode y el destinatario no está verificado
3. Revisa la carpeta de spam/correo no deseado

---

### Error "Template format error" al crear el stack

**Causa**: El archivo YAML tiene errores de formato o está corrupto.

**Solución**: Verifica que estás ejecutando el comando desde la carpeta correcta donde están los archivos `.yml`:

```bash
ls *.yml
```

Deberías ver: `00-pipeline.stack.yml`, `01-database.stack.yml`, etc.

---

## Estructura del Proyecto

```
├── 00-pipeline.stack.yml           # Stack principal: CI/CD Pipeline
├── 01-database.stack.yml           # DynamoDB (3 tablas) + Aurora Serverless v2
├── 02-integration.stack.yml        # EventBridge + SQS + SNS + SES + S3 reportes
├── 03-cognito.stack.yml            # Cognito User Pool + 3 grupos (ADMIN, ORGANIZER, ATTENDEE)
├── 04-artifacts-stack.yml          # S3 bucket para código Lambda
├── 05-logic.stack.yml              # 18 Lambdas + HTTP API + WebSocket API + IAM Roles
├── buildspec.yml                   # Instrucciones de build: empaquetar Lambdas en .zip
├── buildspec-upload-lambdas.yml    # Instrucciones de build: subir .zip a S3
├── Postman_Test_Apis/
│   └── Reto3_UdeM_AWS.postman_collection.json  # Colección de Postman para pruebas
├── codes/
│   ├── auth-login/handler.py                   # Lambda: inicio de sesión
│   ├── auth-signup/handler.py                  # Lambda: registro de usuario
│   ├── buyer-cancel-reservation/handler.py     # Lambda: cancelar reserva
│   ├── buyer-confirm-attendance/handler.py     # Lambda: confirmar asistencia
│   ├── buyer-edit-reservation/handler.py       # Lambda: cambiar asiento
│   ├── buyer-get-all-events/handler.py         # Lambda: listar eventos (buyer)
│   ├── buyer-get-event-seats/handler.py        # Lambda: ver asientos de evento (buyer)
│   ├── buyer-reserve-seat/handler.py           # Lambda: reservar asiento
│   ├── org-create-alert/handler.py             # Lambda: crear alerta
│   ├── org-create-event/handler.py             # Lambda: crear evento
│   ├── org-delete-event/handler.py             # Lambda: eliminar evento
│   ├── org-edit-event/handler.py               # Lambda: editar evento
│   ├── org-generate-report/handler.py          # Lambda: solicitar reporte
│   ├── org-get-all-events/handler.py           # Lambda: listar eventos (organizador)
│   ├── org-get-event-seats/handler.py          # Lambda: ver asientos (organizador)
│   ├── report-processor/handler.py             # Lambda: procesar reportes (SQS consumer)
│   ├── send-reminders/handler.py               # Lambda: enviar recordatorios (cron)
│   └── ws-seat-status/handler.py               # Lambda: WebSocket estado de asientos
└── zips/                                       # Carpeta para los .zip generados (gitignore)
```

### Resumen de Endpoints de la API

| Método   | Ruta                          | Descripción                    | Auth |
| -------- | ----------------------------- | ------------------------------ | ---- |
| `POST`   | `/auth/signup`                | Registrar usuario              | No   |
| `POST`   | `/auth/login`                 | Iniciar sesión                 | No   |
| `GET`    | `/buyer/events`               | Listar todos los eventos       | JWT  |
| `GET`    | `/buyer/events/{eventId}`     | Ver asientos de un evento      | JWT  |
| `POST`   | `/buyer/seats`                | Reservar un asiento            | JWT  |
| `PUT`    | `/buyer/seats/{seatId}`       | Cambiar de asiento             | JWT  |
| `DELETE` | `/buyer/seats/{seatId}`       | Cancelar reserva               | JWT  |
| `POST`   | `/buyer/attendance`           | Confirmar asistencia           | JWT  |
| `GET`    | `/organizer/events`           | Listar eventos del organizador | JWT  |
| `GET`    | `/organizer/events/{eventId}` | Ver asientos de un evento      | JWT  |
| `POST`   | `/organizer/events`           | Crear un evento                | JWT  |
| `PUT`    | `/organizer/events/{eventId}` | Editar un evento               | JWT  |
| `DELETE` | `/organizer/events/{eventId}` | Eliminar un evento             | JWT  |
| `POST`   | `/organizer/reports`          | Solicitar reporte              | JWT  |
| `POST`   | `/organizer/alerts`           | Crear alerta/notificación      | JWT  |

### WebSocket

| Ruta          | Descripción                                 |
| ------------- | ------------------------------------------- |
| `$connect`    | Conexión al WebSocket                       |
| `$disconnect` | Desconexión del WebSocket                   |
| `$default`    | Mensaje por defecto (suscripción a eventos) |
