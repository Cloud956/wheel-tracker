# Frontend Application

A simple Hello World frontend application running on Node.js with Express.

## Running with Docker

### Build the Docker image:
```bash
docker build -t frontend-app .
```

### Run the Docker container:
```bash
docker run -p 3000:3000 frontend-app
```

Then open your browser and navigate to `http://localhost:3000`

## Running locally

### Install dependencies:
```bash
npm install
```

### Start the server:
```bash
npm start
```

The application will be available at `http://localhost:3000`

