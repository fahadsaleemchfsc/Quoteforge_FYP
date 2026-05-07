# ⚡ QuoteForge — AI-Powered Quote & Proposal Generation Tool

> Final Year Project • Forman Christian College University  
> **Advisor:** Dr. Nazim Ashraf | **Co-Advisor:** Faizad Ullah

An AI-powered CRM-integrated tool that automates the generation of professional, compliant, and branded sales quotes and proposals using RAG + LLM.

---

## 📁 Project Structure

```
quoteforge/
├── public/                     # Static assets served directly
│   └── vite.svg               # App favicon
├── src/
│   ├── assets/                # Images, fonts, static files
│   │   ├── images/
│   │   └── fonts/
│   ├── components/            # Reusable UI components
│   │   ├── common/            # StatusBadge, MetricCard, etc.
│   │   ├── layout/            # Sidebar, TopBar (app shell)
│   │   ├── dashboard/         # Dashboard-specific widgets
│   │   ├── templates/         # Template management components
│   │   ├── pricing/           # Pricing rules components
│   │   ├── prompts/           # AI prompt editor components
│   │   ├── crm/               # CRM integration components
│   │   ├── documents/         # Document log components
│   │   ├── users/             # User management components
│   │   └── settings/          # Settings form components
│   ├── context/               # React Context providers
│   │   └── AuthContext.jsx    # Authentication state
│   ├── data/                  # Mock data (replace with API later)
│   │   └── mockData.js
│   ├── hooks/                 # Custom React hooks
│   │   └── index.js           # useAsync, useDebounce, useToggle
│   ├── pages/                 # Route-level page components
│   │   ├── DashboardPage.jsx
│   │   ├── TemplatesPage.jsx
│   │   ├── PricingPage.jsx
│   │   ├── PromptsPage.jsx
│   │   ├── CRMPage.jsx
│   │   ├── DocumentsPage.jsx
│   │   ├── UsersPage.jsx
│   │   └── SettingsPage.jsx
│   ├── services/              # API service layer (Axios)
│   │   └── api.js
│   ├── styles/                # Global CSS / Tailwind
│   │   └── globals.css
│   ├── utils/                 # Constants, helpers
│   │   ├── constants.js
│   │   └── helpers.js
│   ├── App.jsx                # Root component + routes
│   └── main.jsx               # Entry point
├── .env.example               # Environment variable template
├── .eslintrc.cjs              # ESLint config
├── .gitignore
├── index.html                 # HTML shell
├── package.json               # Dependencies & scripts
├── postcss.config.js
├── tailwind.config.js         # Tailwind theme + custom tokens
├── vite.config.js             # Vite build config + aliases
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- **Node.js** ≥ 18.x
- **npm** ≥ 9.x (or use yarn/pnpm)

### Installation

```bash
# Clone the repo
git clone <your-repo-url>
cd quoteforge

# Install dependencies
npm install

# Copy environment variables
cp .env.example .env

# Start development server
npm run dev
```

The app will open at **http://localhost:3000**

### Build for Production

```bash
npm run build
npm run preview  # Preview the production build
```

---

## 🏗 Architecture Overview

This frontend is the **Admin Web Portal** (Module 7 from the SRS) built with:

| Layer              | Technology                  |
|--------------------|-----------------------------|
| **UI Framework**   | React 18 + Vite             |
| **Styling**        | Tailwind CSS 3.4            |
| **Routing**        | React Router DOM 6          |
| **Charts**         | Recharts                    |
| **Icons**          | Lucide React                |
| **HTTP Client**    | Axios (ready for backend)   |
| **Animations**     | Framer Motion (available)   |
| **Notifications**  | React Hot Toast (available) |

### Module Map (SRS → Frontend)

| SRS Module                    | Frontend Page        | Route        |
|-------------------------------|----------------------|--------------|
| Dashboard View                | `DashboardPage`      | `/dashboard` |
| Template Management Interface | `TemplatesPage`      | `/templates` |
| Pricing & Rules Config        | `PricingPage`        | `/pricing`   |
| AI Prompt Management          | `PromptsPage`        | `/prompts`   |
| CRM Integration               | `CRMPage`            | `/crm`       |
| Document Rendering & Delivery | `DocumentsPage`      | `/documents` |
| User & Access Management      | `UsersPage`          | `/users`     |
| System Settings               | `SettingsPage`       | `/settings`  |

---

## 🔌 Connecting to the Backend

The `src/services/api.js` file contains pre-built service functions for every module. To connect to your FastAPI/Django backend:

1. **Set your API URL** in `.env`:
   ```
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   ```

2. **Replace mock data** in each page with the service calls:
   ```jsx
   // Before (mock):
   import { templates } from '@data/mockData';

   // After (real API):
   import { templateService } from '@services/api';
   import { useAsync } from '@hooks';

   const { data: templates, loading } = useAsync(() => templateService.getAll());
   ```

3. **Authentication** is handled via JWT tokens in `AuthContext.jsx` — wire up to your OAuth 2.0 flow.

---

## 🎨 Customization

### Theme Colors
Edit `tailwind.config.js` → `theme.extend.colors.brand` to change the accent color.

### Adding New Pages
1. Create component in `src/pages/NewPage.jsx`
2. Add route in `src/App.jsx`
3. Add nav item in `src/utils/constants.js` → `NAV_ITEMS`
4. Add page meta in `src/utils/constants.js` → `PAGE_META`

---

## 👥 Team

| Name            | Role                              |
|-----------------|-----------------------------------|
| Agha Zain Nadir | Tech Lead & Architecture          |
| Faraz Ali       | AI Engineer                       |
| Fahad Saleem    | Backend Engineer                  |
| Saad Khalid     | Frontend Engineer                 |

---

## 📜 License

Academic project — Forman Christian College University, 2026.
