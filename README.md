# Weather Advisory Agent

WeatherSense is an intelligent, responsive web application that fetches live weather reports for a location and runs it through an LLM integrated with the user's specific context (health condition, activity, travel plan) to generate tailored safety advisories.

---

## 1. Project Directory Structure
```text
weather-advisory-agent/
├── docker-compose.yml        # Docker composition orchestrating DB, Backend, and Frontend
├── .env.example              # Variables template file
├── README.md                 # Setup and deployment documentation
├── backend/
│   ├── Dockerfile            # Multi-stage Python runner container
│   ├── main.py               # FastAPI app initialization
│   ├── requirements.txt      # Dependency list
│   ├── db/                   # Connection, verify script, models, seed script
│   ├── routes/               # API endpoint routing
│   └── services/             # Weather API client & Advisory LLM generator
└── frontend/
    ├── Dockerfile            # Static Nginx web container
    ├── nginx.conf            # Routing rules and reverse API proxy configuration
    ├── index.html            # Main HTML layout
    ├── css/style.css         # Glassmorphism dark-mode stylesheet
    └── js/app.js             # API binding & history hydration module
```

---

## 2. Configuration & Environment Setup

Copy the example env file and fill in your actual credentials:
```bash
# On Linux/macOS
cp .env.example .env

# On Windows (PowerShell)
Copy-Item .env.example .env
```

### Environment Variables
*   `OPENWEATHERMAP_API_KEY`: API token from OpenWeatherMap (free tier).
*   `GEMINI_API_KEY`: API key from Google Gemini Console.
*   `GROQ_API_KEY`: API key from Groq Console (Optional/Alternate).
*   `DB_USER`: Postgres user username.
*   `DB_PASSWORD`: Postgres user password.
*   `DB_NAME`: Postgres database name.

---

## 3. Running Locally with Docker Compose

Build and launch all services (Database, FastAPI, and Nginx) in a unified bridge network:
```bash
docker-compose up --build
```

*   **Frontend Client:** Accessible at `http://localhost` (Port 80)
*   **FastAPI backend API / Interactive Swagger Docs:** Accessible at `http://localhost:8000/docs`
*   **Postgres Database:** Exposed on `localhost:5432`

---

## 4. Deploying to AWS (ECS Fargate & ECR)

Follow these copy-paste CLI commands to build, tag, and publish your containers on AWS ECR, and run them under ECS Fargate.

### Step 4.1: Authenticate Local Docker to ECR
Ensure you have configured your AWS CLI credentials (`aws configure`) and run:
```bash
# Replace <region> with your active AWS region (e.g. us-east-1)
# Replace <aws_account_id> with your 12-digit AWS account ID
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
```

### Step 4.2: Create ECR Registries
```bash
# Create Backend Registry
aws ecr create-repository --repository-name weather-backend --region <region>

# Create Frontend Registry
aws ecr create-repository --repository-name weather-frontend --region <region>
```

### Step 4.3: Build, Tag, and Push Containers
```bash
# Build & Tag Backend Container
docker build -t weather-backend ./backend
docker tag weather-backend:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/weather-backend:latest

# Build & Tag Frontend Container
docker build -t weather-frontend ./frontend
docker tag weather-frontend:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/weather-frontend:latest

# Push Backend to AWS
docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/weather-backend:latest

# Push Frontend to AWS
docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/weather-frontend:latest
```

### Step 4.4: Launch on ECS Fargate
1. **Create ECS Cluster:**
   ```bash
   aws ecs create-cluster --cluster-name weather-advisory-cluster --region <region>
   ```

2. **Register task definitions:**
   Save a `task-definition.json` configuring the CPU/Memory allocations and mapping `weather-backend` and `weather-frontend` containers with environment variables linked to AWS Secrets Manager. Then register it:
   ```bash
   aws ecs register-task-definition --cli-input-json file://task-definition.json --region <region>
   ```

3. **Deploy Fargate Service:**
   ```bash
   aws ecs create-service \
     --cluster weather-advisory-cluster \
     --service-name weather-service \
     --task-definition weather-task \
     --desired-count 1 \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[<subnet-id-1>,<subnet-id-2>],securityGroups=[<security-group-id>],assignPublicIp=ENABLED}" \
     --region <region>
   ```
