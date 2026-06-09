# VerdictBox — AI Moderation & Debate Platform

<p align="center">
  <img src="docs/assets/banner.svg" alt="VerdictBox Banner" width="100%">
</p>

<p align="center">
  <a href="#demo"><img src="https://img.shields.io/badge/Live%20Preview-Local%20Host-00C853?style=for-the-badge" alt="Local preview"></a>
  <a href="#features"><img src="https://img.shields.io/badge/AI%20Analysis-Toxicity%20%7C%20Fallacies-1976D2?style=for-the-badge" alt="AI"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask" alt="Flask"></a>
  <a href="#database--schema"><img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql" alt="MySQL"></a>
</p>

<p align="center"><strong>Maintainers:</strong> Umais Ahmed (24K-1003) • Abeer Siddiqui (24K-0538) • Musab Sheikh (24K-0862)</p>

VerdictBox is a web-based debate and moderation platform that leverages machine learning to analyze arguments, detect harmful content, identify logical fallacies, and generate AI-assisted verdicts. It combines structured debates, automated moderation, and community-driven engagement into a single platform.

---

## Table of Contents

* [Demo](#demo)
* [Why VerdictBox](#why-verdictbox)
* [Features](#features)
* [Application Screenshots](#-application-screenshots)
* [Quick Start](#quick-start)
* [Architecture & Tech](#architecture--tech)
* [ML Pipeline](#ml-pipeline)
* [Database & Schema](#database--schema)
* [API & Routes](#api--routes-key-endpoints)
* [Suggested Demo Checklist](#suggested-demo-checklist-for-recruiters)
* [Credits & License](#credits--license)

---

## Demo

Run locally and open `http://localhost:5000` for a full preview.

For presentations and demonstrations, consider replacing the banner with a short GIF (`docs/assets/demo.gif`) showcasing the dispute creation → submission → verdict workflow.

---

## Why VerdictBox

* Structured debates with evidence-based discussions
* AI-assisted verdict generation and moderation
* Detection of toxicity, sarcasm, sentiment, and logical fallacies
* Appeals and moderation workflows for fairness
* Educational value for classrooms and debate communities
* Reputation, badges, and leaderboard systems for engagement

---

## Features

* Real-time dispute lifecycle: create, submit, resolve, and appeal
* Machine learning pipeline for argument analysis
* Public and private dispute modes
* Community reporting and moderation tools
* Automated flagging and escalation workflows
* Leaderboards, badges, and reputation tracking
* Administrative audit logs and appeal reviews
* Analytics dashboard with insights and summaries

---

## 📸 Application Screenshots

### 🏠 Home Feed, Search & Discovery

Browse active disputes, search discussions, and explore trending debates across the platform.

<p align="center">
  <img src="https://github.com/user-attachments/assets/0ceb9255-060d-4f04-b538-dcc598856728" width="900">
</p>

### ➕ Create a Dispute

Create structured debates by defining the topic, description, and participants.

<p align="center">
  <img src="https://github.com/user-attachments/assets/eba88162-4ed4-4b9a-aa1a-23d99e1e1a83" width="900">
</p>

### 📋 Dispute Directory

View ongoing and completed disputes with status tracking and participant information.

<p align="center">
  <img src="https://github.com/user-attachments/assets/f6bbb32e-3488-4e18-8c00-c4bf86b0a107" width="900">
</p>

### ⚖️ AI Verdict & Analysis

Detailed verdict page displaying confidence scores, AI reasoning, sentiment analysis, and fallacy detection results.

<p align="center">
  <img src="https://github.com/user-attachments/assets/d51c763f-9f08-4930-a8ad-1ed7c96193f3" width="900">
</p>

### 🏆 Leaderboard & Rankings

Track top-performing users through the reputation and ranking system.

<p align="center">
  <img src="https://github.com/user-attachments/assets/6fcf42ee-408f-43ac-aa50-31b27c35abda" width="900">
</p>

### 📊 User Dashboard

Personalized dashboard providing activity insights, dispute history, and user statistics.

<p align="center">
  <img src="https://github.com/user-attachments/assets/0f2fd5c1-05b9-435a-a51a-0daeeae48af0" width="900">
</p>

## 🛡️ Administration & Moderation

### 🚩 Flagged Issues Management

<p align="center">
  <img src="https://github.com/user-attachments/assets/74ed2bb4-9cfc-488f-a99c-461155420599" width="900">
</p>

### 📝 Administrative Audit Logs

<p align="center">
  <img src="https://github.com/user-attachments/assets/e8ccebee-ba77-4669-9704-959e52572990" width="900">
</p>

### 🔄 Pending Appeals Queue

<p align="center">
  <img src="https://github.com/user-attachments/assets/8daf9581-e7db-440e-b2ce-0dc47c24a85b" width="900">
</p>

---

## Quick Start

### 1. Clone the Repository

```powershell
git clone <your-repo-url>
cd verdictbox
```

### 2. Create & Activate a Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create `config/.env`:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost/verdictbox
SECRET_KEY=replace-with-random-secret
```

### 5. Initialize & Seed the Database

```powershell
.\run_project.ps1 -InitDb -SeedDb
```

### 6. Run the Application

```powershell
python app.py
```

Open:

```text
http://localhost:5000
```

---

## Architecture & Tech

### Backend

* Flask
* Flask-Login
* SQLAlchemy

### Database

* MySQL
* SQL Scripts
* Stored Procedures
* Triggers

### Machine Learning

* Scikit-learn
* Pandas
* NumPy

### Frontend

* Jinja2 Templates
* Vanilla JavaScript
* CSS

### Project Structure

```text
verdictbox/
├── ai/
├── config/
├── core/
├── db/
├── docs/
├── routes/
├── static/
├── templates/
└── utils/
```

---

## ML Pipeline

The central function `run_full_pipeline()` processes dispute submissions and returns structured results including:

* Toxicity analysis
* Sentiment analysis
* Sarcasm detection
* Logical fallacy detection
* Confidence scoring
* Winner prediction
* AI-generated reasoning

Possible statuses:

* `resolved`
* `flagged`
* `error`

Flagged content automatically triggers moderation workflows and administrative review.

---

## Database & Schema

Key database design features include:

* One submission per participant using unique constraints
* Structured storage of AI verdicts and ML outputs
* Community reports and automated system flags
* Appeal management workflows
* Automated moderation escalation through triggers

Additional database documentation is available in:

## Credits & License

Made with ❤️ by the VerdictBox Team.

### Team Members

* **Umais Ahmed** (24K-1003)
* **Abeer Siddiqui** (24K-0538)
* **Musab Sheikh** (24K-0862)

### License

This project is licensed under the MIT License. See the `LICENSE` file for details.

```
```
