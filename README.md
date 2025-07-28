# Zscaler Multi-Source URL Category Sync

This script automates the process of updating a Zscaler custom URL category from a dynamic, remote list of URLs or IPs. It is designed to be run in a Docker container, typically triggered by a cron job.

## Features

-   Fetches URL lists from remote sources (TXT, CSV, or JSON).
-   Intelligently parses complex and nested JSON formats.
-   Creates the Zscaler URL category if it doesn't exist.
-   Updates the category only if changes are detected between the source and Zscaler.
-   All configuration and secrets are managed via a `.env` file.

---

## Prerequisites

-   Docker
-   Docker Compose

---

## Setup and Configuration

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2.  **Create the environment file:**
    Copy the example configuration file to a new `.env` file.
    ```bash
    cp .env.example .env
    ```

3.  **Edit the `.env` file:**
    Open the `.env` file in a text editor and fill in your specific values, especially:
    -   `CLIENT_ID`
    -   `CLIENT_SECRET`
    -   `VANITY_DOMAIN`
    -   `CATEGORY_NAME`
    -   `URL_LIST_SOURCE`

---

## Usage

1.  **Build and Start the Container:**
    This command builds the Docker image and starts the container in the background. The container will remain running, ready for script execution.
    ```bash
    docker-compose up -d --build
    ```

2.  **Run the Sync Script Manually:**
    To trigger the script manually and test your configuration, use `docker-compose exec`:
    ```bash
    docker-compose exec app python3 multi-url-category-sync.py
    ```

3.  **Automate with Cron (Example):**
    To run the script automatically every hour, you can add an entry to your host machine's crontab.

    First, run `crontab -e`. Then, add the following line, making sure to use the absolute path to your project directory:

    ```cron
    # Run the Zscaler sync script every hour
    0 * * * * cd /path/to/your/project && /usr/bin/docker-compose exec app python3 multi-url-category-sync.py >> /var/log/zscaler-sync.log 2>&1
    ```

---

## File Overview

-   `multi-url-category-sync.py`: The main Python script.
-   `Dockerfile`: Defines the Docker image for the application.
-   `docker-compose.yml`: Manages the Docker container and environment variables.
-   `requirements.txt`: Python package dependencies.
-   `.env.example`: Template for the required environment variables.
-   `.gitignore`: Specifies files to be excluded from Git version control (like the secret `.env` file).