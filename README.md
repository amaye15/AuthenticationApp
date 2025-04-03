---
title: AuthenticationApp
emoji: 🔥
colorFrom: yellow
colorTo: yellow
sdk: docker
pinned: false
license: apache-2.0
short_description: An app demonstrating Gradio, FastAPI, Docker & SQL DB
app_file: app/main.py
python_version: 3.12
port: 7860
---

# AuthenticationApp

A secure authentication application with real-time notifications built using FastAPI, SQLite, WebSockets, and modern JavaScript. The app demonstrates full-stack development practices including secure password handling, token-based authentication, and real-time communication.

## Features

- 🔐 Secure user registration and login
- 🔑 Token-based authentication
- 📲 Real-time notifications via WebSockets
- 🎨 Modern responsive UI with auto light/dark mode
- 🐳 Docker containerization
- 🧪 Load testing utilities
- 📊 API documentation with Swagger UI

## Live Demo

You can access the live demo at:
[https://amaye15-authenticationapp.hf.space/](https://amaye15-authenticationapp.hf.space/)

API documentation is available at:
[https://amaye15-authenticationapp.hf.space/docs](https://amaye15-authenticationapp.hf.space/docs)

## Installation and Setup

### Local Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/authenticationapp.git
   cd authenticationapp
   ```

2. Create and activate a virtual environment:
   ```bash
   uv venv --python 3.12 
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

### Using Docker

1. Build the Docker image:
   ```bash
   docker build -t auth-app .
   ```

2. Run the container:
   ```bash
   docker run -p 7860:7860 auth-app
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:7860
   ```

## Testing

### API Testing

The application includes a test script (`tests/api.py`) that simulates user registration, login, and basic actions. It also provides load testing capabilities.

#### Run Load Tests

Local load testing:
```bash
uv run tests/api.py load
```

Remote load testing (against the deployed app):
```bash
uv run tests/api.py --remote load
```

## Security Notes

- The app uses bcrypt for password hashing
- Authentication is handled via signed session tokens
- A non-root user is used in the Docker container
- The application includes a healthcheck configuration

## API Documentation

Interactive API documentation is available when the app is running:
- Swagger UI: http://localhost:7860/docs
- ReDoc: http://localhost:7860/redoc

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.




