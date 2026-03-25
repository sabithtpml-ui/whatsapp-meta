# WhatsApp AI Integration for Odoo 17

A standalone Odoo 17 application that connects **WhatsApp Meta Cloud API** with an **LLM-powered chatbot** (Claude/GPT), deeply integrated into Odoo's Sales, Discuss, Contacts, and Reporting modules.

---

## Features

### 1. WhatsApp ↔ Odoo Messaging
- **Auto-notify on Sale Order confirmation** – When a SO is confirmed, the customer receives a WhatsApp message with order details (template or plain text).
- **Incoming messages appear in Odoo Discuss** – Each WhatsApp conversation gets its own Discuss channel. Replies from customers pop up in real time.
- **Send messages from anywhere** – Smart buttons on Contacts and Sale Orders let you compose and send WhatsApp messages directly.
- **Full message logging** – Every message (incoming/outgoing) is logged with delivery status tracking (sent → delivered → read → failed).

### 2. AI Chatbot (LLM-Powered)
When a customer sends a WhatsApp message, the AI chatbot can:
- **Create Sale Orders** via natural language ("I want 5 units of Product X")
- **Query customer info** ("What's my last order?", "Do I have pending invoices?")
- **Generate reports** ("Give me a sales summary for the last 30 days", "Who are my top customers?")
- **Answer product questions** ("Is Product Y in stock?", "What's the price of Z?")
- **Multi-turn conversations** with full context memory per conversation

### 3. Human Takeover
- One-click switch from AI to human handling
- Agent assignment
- Resume AI when done

### 4. Standalone Dashboard
- KPI cards (active conversations, messages today, failed, AI-handled)
- Recent conversations & messages feed
- Quick action buttons
- Fully OWL-based, runs as a client action

### 5. REST API
External systems can interact headlessly:
```
GET  /api/whatsapp/health
POST /api/whatsapp/send
GET  /api/whatsapp/conversations
GET  /api/whatsapp/conversations/<id>/messages
POST /api/whatsapp/chatbot/ask
GET  /api/whatsapp/reports/sales_summary
GET  /api/whatsapp/reports/top_products
GET  /api/whatsapp/reports/top_customers
GET  /api/whatsapp/reports/outstanding
```

---

## Architecture

```
┌──────────────┐       Webhook (POST)       ┌──────────────────┐
│   WhatsApp   │ ◄─────────────────────────► │  Odoo Controller │
│   Meta API   │       Send (POST)           │  /whatsapp/      │
└──────────────┘                             │  webhook         │
                                             └────────┬─────────┘
                                                      │
                    ┌─────────────────────────────────┼──────────────────┐
                    │                                 │                  │
              ┌─────▼──────┐   ┌──────────────┐  ┌───▼────────┐  ┌─────▼──────┐
              │  whatsapp.  │   │  whatsapp.   │  │  whatsapp. │  │  Discuss   │
              │  message    │   │ conversation │  │  llm.engine│  │  Channel   │
              │  (logging)  │   │  (threads)   │  │  (AI brain)│  │  (UI chat) │
              └─────────────┘   └──────────────┘  └─────┬──────┘  └────────────┘
                                                        │
                                            ┌───────────┼───────────┐
                                            │           │           │
                                      ┌─────▼──┐ ┌─────▼──┐ ┌─────▼──────┐
                                      │ Create │ │ Query  │ │  Generate  │
                                      │  SO    │ │Partner │ │  Reports   │
                                      └────────┘ └────────┘ └────────────┘
```

---

## Installation

### Prerequisites
- Odoo 17 Community or Enterprise
- Python 3.10+
- `requests` library (usually pre-installed with Odoo)

### Steps

1. **Copy module** to your Odoo addons directory:
   ```bash
   cp -r whatsapp_ai_integration /path/to/odoo/addons/
   ```

2. **Update the apps list** in Odoo:
   ```
   Settings → General Settings → Developer Tools → Update Apps List
   ```

3. **Install the module**:
   ```
   Search for "WhatsApp AI" in Apps → Install
   ```

4. **Configure the module** (see below).

---

## Configuration

### Step 1: Meta WhatsApp Business API

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Create an app → Add WhatsApp product
3. In **WhatsApp → API Setup**, note your:
   - Phone Number ID
   - WhatsApp Business Account ID
4. Generate a **permanent access token** (System Users → Generate Token → whatsapp_business_messaging)
5. In **WhatsApp → Configuration → Webhooks**:
   - Callback URL: `https://your-odoo-domain.com/whatsapp/webhook`
   - Verify Token: use the same value you'll set in Odoo
   - Subscribe to: `messages`, `message_deliveries`

### Step 2: Odoo Configuration

Go to **Settings → WhatsApp AI**:

| Field | Value |
|-------|-------|
| Phone Number ID | From Meta API Setup |
| Business Account ID | From Meta API Setup |
| Access Token | Your permanent token |
| Webhook Verify Token | Must match Meta webhook config |
| API Version | `v21.0` (or latest) |

Click **Test Connection** to verify.

### Step 3: LLM Configuration

| Field | Value |
|-------|-------|
| LLM Provider | Anthropic (Claude) or OpenAI (GPT) |
| API Key | Your API key |
| Model | `claude-sonnet-4-20250514` or `gpt-4o` |
| System Prompt | (optional) Override the default AI personality |

Click **Test LLM** to verify.

### Step 4: Feature Toggles

| Feature | Description |
|---------|-------------|
| Auto-send on SO Confirmation | Sends WhatsApp when SO is confirmed |
| Enable AI Chatbot | AI processes incoming messages |
| SO Template Name | Name of your approved WhatsApp template (leave blank for plain text) |

---

## WhatsApp Template Setup

For **proactive** messages (like SO notifications), Meta requires pre-approved templates.

1. Go to **Meta Business Manager → WhatsApp → Message Templates**
2. Create a template, e.g. `order_confirmation`:
   ```
   Hello {{1}},
   Your order {{2}} has been confirmed!
   Total: {{3}}
   Reply to this message for support.
   ```
3. Submit for approval
4. Enter the template name in Odoo Settings → WhatsApp AI → SO Template Name

> **Note:** If you leave the template name blank, the module sends plain text messages. Plain text only works within the **24-hour messaging window** (i.e., after the customer messages you first).

---

## Usage

### Sale Orders
- Confirm a Sale Order → customer gets WhatsApp notification automatically
- Click the **WhatsApp** smart button on any SO to see related messages
- Click **📱 Send WhatsApp** to manually re-send

### Contacts
- Click the **WhatsApp** smart button to see all conversations
- Click **Send WhatsApp** to compose a new message

### Dashboard
- Navigate to **WhatsApp AI → Dashboard** for the full overview
- Click any KPI card to drill down

### AI Chatbot Examples

Customers can text things like:
- "Hi, I'd like to order 10 units of Widget A"
- "What's the status of my last order?"
- "Do I have any unpaid invoices?"
- "What products do you have in stock?"
- "Give me a sales report for this month"
- "Who are your top 5 customers?"

The AI understands context, asks follow-up questions when needed, and executes Odoo operations directly.

---

## REST API Usage

### Authentication
Pass your Odoo API key in the `X-API-KEY` header:
```bash
curl -H "X-API-KEY: your_api_key" https://your-odoo.com/api/whatsapp/health
```

### Send a message
```bash
curl -X POST https://your-odoo.com/api/whatsapp/send \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your_key" \
  -d '{"phone": "971501234567", "message": "Hello from the API!"}'
```

### Ask the chatbot
```bash
curl -X POST https://your-odoo.com/api/whatsapp/chatbot/ask \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your_key" \
  -d '{"phone": "971501234567", "question": "What are my recent orders?"}'
```

---

## Module Structure

```
whatsapp_ai_integration/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── res_config_settings.py    # Settings UI
│   ├── whatsapp_api.py           # Meta Cloud API wrapper
│   ├── llm_engine.py             # AI brain (Claude/GPT)
│   ├── whatsapp_message.py       # Message storage
│   ├── whatsapp_conversation.py  # Conversation threads + Discuss
│   ├── sale_order.py             # SO auto-notification
│   └── res_partner.py            # Contact WhatsApp fields
├── controllers/
│   ├── webhook.py                # Meta webhook handler
│   └── standalone_api.py         # REST API endpoints
├── wizards/
│   └── whatsapp_compose_wizard.py
├── views/
│   ├── res_config_settings_views.xml
│   ├── whatsapp_message_views.xml
│   ├── whatsapp_conversation_views.xml
│   ├── sale_order_views.xml
│   ├── res_partner_views.xml
│   ├── whatsapp_compose_wizard_views.xml
│   └── menu_views.xml
├── data/
│   ├── ir_cron_data.xml
│   └── mail_template_data.xml
├── security/
│   └── ir.model.access.csv
├── static/
│   ├── description/icon.png
│   └── src/
│       ├── js/dashboard.js       # OWL Dashboard component
│       ├── xml/dashboard.xml     # Dashboard template
│       └── css/whatsapp.css      # Dashboard styles
└── README.md
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Webhook not receiving messages | Ensure your Odoo instance is HTTPS and publicly accessible. Check Meta webhook subscription. |
| "Template not approved" error | Use plain text (leave template name blank) or wait for Meta approval. |
| AI responses are slow | The LLM API call adds 2-5s latency. This is normal. |
| Messages stuck in "sent" | Meta status webhooks may be delayed. Statuses update asynchronously. |
| Partner not found for phone | Ensure partners have `Mobile` or `Phone` filled with international format. |

---

## License

LGPL-3.0
