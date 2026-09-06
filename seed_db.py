"""Create and seed the SQLite database used by the Streamlit app."""
from database import initialize_database, seed_criteria

if __name__ == "__main__":
    initialize_database()
    seed_criteria()
    print("SQLite database initialized and criteria seeded.")
