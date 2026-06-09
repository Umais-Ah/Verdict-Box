# VerdictBox

<p align="center">
  <img src="docs/assets/banner.png" alt="VerdictBox Banner" width="100%">
</p>

<p align="center">
  <a href="#-demo"><img src="https://img.shields.io/badge/Live%20Preview-Available-00C853?style=for-the-badge&logo=vercel" alt="Live Preview"></a>
  <a href="#-features"><img src="https://img.shields.io/badge/AI%20Moderation-Enabled-1976D2?style=for-the-badge&logo=openai" alt="AI Moderation"></a>
  <a href="#-setup"><img src="https://img.shields.io/badge/Flask-App-000000?style=for-the-badge&logo=flask" alt="Flask"></a>
  <a href="#-database"><img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql" alt="MySQL"></a>
</p>

<p align="center">
  <b>VerdictBox</b> is an AI-powered dispute resolution platform where users create debates, submit arguments, receive machine-assisted verdicts, and interact through comments, reports, appeals, badges, leaderboards, and analytics.
</p>

---

## ✨ Overview

VerdictBox combines debate management, community moderation, and machine learning in one platform. It supports both public and private disputes, automated verdict generation, moderation workflows, and user reputation features.

## 🎯 Key Features

- 🤖 AI verdict generation using toxicity, sentiment, sarcasm, and fallacy analysis
- 🧠 Full dispute lifecycle from creation to resolution
- 💬 Public and private comments
- 🗳️ Spectator engagement voting for public disputes
- 🚩 Report and escalation system for moderation
- 🔁 Appeals workflow for disputants
- 🏆 Badges, reputation, and leaderboard ranking
- 📊 Statistics dashboard with charts and insights
- 🔒 Public and private moderation modes

## 🖼️ Screenshots

<p align="center">
  <img src="docs/assets/screenshot-home.png" alt="Home Screen" width="48%">
  <img src="docs/assets/screenshot-dispute.png" alt="Dispute Screen" width="48%">
</p>

<p align="center">
  <img src="docs/assets/screenshot-verdict.png" alt="Verdict Screen" width="48%">
  <img src="docs/assets/screenshot-dashboard.png" alt="Dashboard Screen" width="48%">
</p>

> Add your real screenshots inside `docs/assets/` and keep these file names for the cleanest GitHub preview.

## 🎥 Video Preview

<p align="center">
  <a href="https://www.youtube.com/watch?v=YOUR_VIDEO_ID">
    <img src="docs/assets/video-preview.png" alt="Watch the VerdictBox demo" width="85%">
  </a>
</p>

> Replace the link above with your demo video and the image with a thumbnail or GIF preview.

## 🚀 Demo Flow

1. Register or log in
2. Create or join a dispute
3. Submit arguments
4. Wait for the AI verdict
5. Comment, vote, report, or appeal depending on your role

## 🛠️ Tech Stack

- **Frontend:** HTML, CSS, JavaScript, Jinja2
- **Backend:** Flask, Flask-Login, SQLAlchemy
- **Database:** MySQL
- **AI/ML:** Python ML pipeline for verdict scoring
- **Libraries:** pandas, NumPy, scikit-learn, and related Python packages

## 📁 Project Structure

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

## ⚙️ Setup

### 1) Install dependencies

```powershell
pip install -r requirements.txt
```

### 2) Configure environment

Create `config/.env` and add your MySQL credentials.

### 3) Run the app

```powershell
python app.py
```

Or use the Windows helper script:

```powershell
.\run_project.ps1 -InitDb -SeedDb
```

## 🗄️ Database

The project uses MySQL and includes SQL scripts for schema, seeds, triggers, views, and procedures inside the `db/` folder.

## 👥 User Roles

- **Disputant:** creates disputes, submits arguments, and can appeal
- **Spectator:** comments, votes, and reports public disputes
- **Admin:** moderates disputes, reviews reports, and handles appeals

## 📚 Documentation

- [Setup Guide](SETUP_GUIDE.md)
- [Database Explanation](DATABASE_EXPLANATION.md)
- [Moderation System Design](docs/MODERATION_SYSTEM_DESIGN.md)

## 📌 Highlights

- Public disputes support community interaction
- Private disputes are invite-only and more controlled
- Appeals can trigger AI re-analysis
- Reports can escalate disputes automatically
- Stats and leaderboard pages show platform activity

## 🤝 Contributing

If you want to improve VerdictBox, you can add better UI screenshots, a short demo video, or new moderation features.

## 📄 License

Add your preferred license here if you plan to publish the repository.
