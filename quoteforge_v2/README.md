# QuoteForge — AI-Powered Quote & Proposal Generation Tool

> **Final Year Project** — Department of Computer Science, Forman Christian College University
>
> Team: Agha Zain Nadir · Faraz Ali · Fahad Saleem · Saad Khalid
> Advisor: Dr Nazim Ashraf | Co-Advisor: Faizad Ullah

---

## Overview

QuoteForge is a CRM-integrated automation system that generates professional, compliant, and brand-consistent sales quotes and proposals using AI (RAG + LLM). It integrates with Salesforce and HubSpot via OAuth 2.0, applies configurable pricing and compliance rules (SOC 2, GDPR, PPRA), and renders documents in PDF/DOCX formats.

## Tech Stack

| Layer       | Technology                          |
| ----------- | ----------------------------------- |
| Frontend    | React 18 + Vite + Tailwind CSS     |
| Backend     | FastAPI / Django REST Framework     |
| Database    | PostgreSQL                          |
| AI          | GPT-class LLM with RAG pipeline    |
| Documents   | ReportLab / python-docx             |
| Integration | Salesforce & HubSpot REST APIs      |
| Deployment  | Docker on AWS EC2                   |

## Project Structure

```
quoteforge/
├── public/                  # Static assets
├── src/
│   ├── assets/              # Images, fonts
│   ├── components/
│   │   ├── layout/          # Sidebar, TopBar
│   │   ├── ui/              # StatusBadge, MetricCard, etc.
│   │   └── charts/          # Chart wrapper components
│   ├── constants/           # Navigation config, mock data
│   ├── context/             # React context (Auth, Theme)
│   ├── hooks/               # Custom hooks (useApi, useDebounce)
│   ├── pages/               # Page-level components
│   │   ├── Dashboard.jsx
│   │   ├── Templates.jsx
│   │   ├── Pricing.jsx
│   │   ├── Prompts.jsx
│   │   ├── CRM.jsx
│   │   ├── Documents.jsx
│   │   ├── Users.jsx
│   │   └── Settings.jsx
│   ├── services/            # API client & service modules
│   ├── styles/              # Global CSS + Tailwind
│   ├── utils/               # Helper functions
│   ├── App.jsx              # Root component with routing
│   └── main.jsx             # Entry point
├── .env.example             # Environment template
├── index.html               # HTML shell
├── package.json
├── tailwind.config.js
├── vite.config.js
└── README.md
```

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **npm** or **yarn**

### Installation

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd quoteforge

# 2. Install dependencies
npm install

# 3. Copy environment template
cp .env.example .env.local

# 4. Start development server
npm run dev
```

The app will open at **http://localhost:3000**.

### Build for Production

```bash
npm run build     # outputs to dist/
npm run preview   # preview the production build
```

## Modules

| Module             | Description                                           |
| ------------------ | ----------------------------------------------------- |
| **Dashboard**      | KPI metrics, trend charts, integration health, activity feed |
| **Templates**      | Upload, edit, preview quote/proposal templates         |
| **Pricing & Rules**| Discount tiers, tax rules, compliance clauses (SOC 2, GDPR, PPRA) |
| **AI Prompts**     | Manage prompt templates for each document section      |
| **CRM Integrations** | OAuth connections to Salesforce/HubSpot, field mapping |
| **Documents**      | Audit log of generated documents, delivery tracking    |
| **Users & Access** | Role-based access control (Admin, Manager, Rep)        |
| **Settings**       | Organization, AI, email, and security configuration    |

## Connecting to the Backend

The Vite dev server proxies `/api` → `http://localhost:8000`. The service files in `src/services/` are pre-wired with axios and JWT auth. Replace the mock data in `src/constants/mockData.js` with real API calls as the backend is built.

## License

Academic use only — Forman Christian College University FYP 2025-26.
