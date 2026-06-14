# Smart Vehicle Parking System

A full-featured real-time Smart Vehicle Parking System built with Flask, with support for local SQLite development and Render PostgreSQL deployment.

## Quick Start
- Local development: copy settings from `.env.example` or use `.env`, then run `python app.py`
- Deployment: follow the step-by-step guide in `DEPLOY.md`
- GitHub repository: `https://github.com/osaguonae70-maker/smart-parking-system.git`

## Features
- **Real-time Dashboard**: Dynamic grid of 50 slots updating every 3 seconds via AJAX.
- **Separate Portals**: Dedicated Landing Page at `/` to choose between User Portal (`/portal`) and Admin Dashboard (`/admin`).
- **Dynamic Slot Management**: Automatically assigns the next available slot.
- **Authentication**: Secure login/registration using Flask-Login and password hashing.
- **QR Code System**: Generates a unique QR code for each parked vehicle; supports simulated scanning for exit.
- **Admin Dashboard**: Overview of all slots, occupancy stats, and real-time revenue tracking in Naira (₦).
- **Revenue Reports**: Export transaction history to CSV.
- **Map Integration**: Leaflet.js (OpenStreetMap) showing parking location (Nasarawa State University Keffi, Nigeria) and availability.
- **IoT Integration**: API endpoint for sensor updates with a dedicated simulation script.
- **Search & Filter**: Find vehicles quickly and filter by status (Available/Occupied).
- **Responsive Design**: Mobile-friendly UI with modern Bootstrap 5 styling.

## Project Structure
- `app.py`: Main Flask application and API routes.
- `models.py`: SQLAlchemy database models (User, Slot, Transaction).
- `auth.py`: Authentication logic (Login, Register, Logout).
- `sensor_simulation.py`: IoT sensor simulation script.
- `templates/`: HTML templates (Dashboard, Admin, Auth).
- `static/`: CSS, JS, and generated QR codes.

## Local Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python app.py
   ```
   The application will initialize the database and 50 parking slots automatically on first run.

3. **Access the System**:
   - Open your browser and go to: `http://127.0.0.1:5000`
   - Register a new account to start parking vehicles.

4. **Simulate IoT Sensors (Optional)**:
   While the Flask app is running, open a new terminal and run:
   ```bash
   python sensor_simulation.py
   ```
   This will randomly update slot statuses (occupied/available) to simulate real-world sensors.

## Render Deployment

This project is ready for deployment on `Render` with an external `PostgreSQL` database such as `Neon`.

### Files Added for Render
- `render.yaml`: Creates one Python web service and prompts for an external `DATABASE_URL`.
- `wsgi.py`: Runs the Flask app through `gunicorn` and initializes the database on startup.

### Environment Variables
- `SECRET_KEY`: Flask secret key for sessions and login security.
- `DATABASE_URL`: Paste your external PostgreSQL connection string in Render.
- `FLASK_DEBUG=0`: Keeps the production server in non-debug mode.
- `ADMIN_LOCAL_ONLY=0`: Allows the admin pages to work on the hosted deployment.

### Deploy Steps
1. Push this project to GitHub.
2. Create a free PostgreSQL database at [Neon](https://neon.com/) or another provider and copy its connection string.
3. Sign in to [Render](https://render.com/).
4. Choose **New +** then **Blueprint**.
5. Select the GitHub repository that contains this project.
6. Render will detect `render.yaml` and create the web service `smart-parking-system`.
7. When Render prompts for `DATABASE_URL`, paste the external PostgreSQL connection string.
8. Click **Apply** to start the deployment.
9. After deployment finishes, open the generated Render URL.

### Notes
- The app still uses local `SQLite` automatically when `DATABASE_URL` is not set.
- On Render, the app switches automatically to PostgreSQL using the provided external connection string.
- `gunicorn` serves both the frontend templates and the Flask backend from one Render web service.

## Usage Guide
- **Parking**: Log in, enter your vehicle number, and click "Assign Slot & Park". A QR ticket will be generated.
- **Exiting**: Use the "Release" form. You can manually enter the vehicle number/slot ID or click the QR icon to paste your QR ticket data.
- **Admin**: Access `/admin` to see detailed logs and download revenue reports.
- **Map**: View the live location and availability marker on the main dashboard.

## Security Features
- Password hashing with Werkzeug (PBKDF2:SHA256).
- Protected routes using `@login_required`.
- Input validation and duplicate vehicle prevention.
