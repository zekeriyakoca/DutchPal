# 🇳🇱 DutchPal

**Learn Dutch naturally — with a little help from your pal.**

---

## 🛠️ Set Up the Environment

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

🚀 Run the API
Start the FastAPI backend:
```bash
uvicorn main:app --reload
```

💻 Launch the UI
```bash
streamlit run ui.py
```

---

## 📂 Tools and Utilities

The project includes a variety of tools and utilities for processing, analyzing, and enhancing Dutch language learning materials. These tools handle tasks such as OCR, embedding generation, grammar processing, and interaction with AI models.

For detailed information about the tools, check out the [Tools README](tools/README.md).

## Deployment to Local Server

For detailed instructions on deploying the FastAPI application to a local Kubernetes cluster, refer to the [Deployment to Local Kubernetes Guide](docs/Deployment-to-local-k8s.md).

> **Note**: The `Deployment-to-local-k8s.md` file is ignored in the repository (`.gitignore`) since this repository is public, and it may contain sensitive or environment-specific deployment details.