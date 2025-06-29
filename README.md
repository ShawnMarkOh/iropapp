# iropapp

WIP - A weather dashboard for airline irregular operations (IROPS).

## Running with Docker

This application is designed to be run with Docker and Docker Compose.

### Prerequisites

- Docker
- Docker Compose

### Setup

1.  **Create an environment file:**
    Copy the example environment file to a new file named `.env`.

    ```bash
    cp .env.example .env
    ```

2.  **Configure your environment:**
    Open the `.env` file and set your desired `ADMIN_USERNAME` and `ADMIN_PASSWORD`. You should also generate a new `SECRET_KEY` for production environments using the command provided in the file.

3.  **Build and run the container:**
    Use Docker Compose to build and start the application.

    ```bash
    docker-compose up --build
    ```

    The `--build` flag is only necessary the first time or when dependencies change. For subsequent runs, you can just use `docker-compose up`.

4.  **Access the application:**
    The dashboard will be available at [http://localhost:8550](http://localhost:8550).

### Admin User

The admin user is automatically created or updated on application startup based on the `ADMIN_USERNAME` and `ADMIN_PASSWORD` variables in your `.env` file. You can log in with these credentials at the `/login` page.
