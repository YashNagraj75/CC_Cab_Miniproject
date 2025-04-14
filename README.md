## Tools and Frameworks Used

This project utilizes the following tools and frameworks:

*   **FastAPI:** A modern, fast (high-performance) web framework for building APIs with Python, based on standard Python type hints. Used for creating the API endpoints.
*   **Pydantic:** Used by FastAPI for data validation, serialization/deserialization (converting data between Python objects and JSON), and automatic generation of API documentation (Swagger UI/ReDoc).
*   **SQLAlchemy:** A SQL toolkit and Object Relational Mapper (ORM). Used here primarily via its Core features (`text()`) to interact with the database using SQL queries within the FastAPI application.
*   **Uvicorn:** An ASGI (Asynchronous Server Gateway Interface) server used to run the FastAPI application.
*   **SQLite:** A C-language library that implements a small, fast, self-contained, high-reliability, full-featured, SQL database engine. Used as the database backend for storing application data in a single `.db` file. CC_Cab_Miniproject
