# RedDrop

RedDrop is a blood bank management system designed to connect donors, hospitals, and administrators in one platform. It helps manage blood requests, donor registration, hospital approvals, blood stock, donation records, and notification workflows efficiently.

## Features

- Donor registration and profile management
- Hospital registration and login
- Blood request creation and tracking
- Blood stock management
- Admin dashboard for monitoring and approvals
- Donation certificate generation
- Donor leaderboard
- Chatbot assistance for users
- Notification and escalation tracking
- Secure authentication with JWT

## Tech Stack

- Backend: Django, Django REST Framework
- Authentication: JWT / Token-based auth
- Task Queue: Celery
- Frontend: HTML, Tailwind CSS
- Database: Your configured Django database
- Background Jobs: Redis + Celery

## Screenshots

Add screenshots of the most important screens here.

## Installation

### Backend
```bash
cd Backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver

cd Frontend
npm install
npm run dev

```



