# 🇳🇱 DutchPal

**Learn Dutch naturally — with a little help from your pal.**

---

## 🛠️ Set Up the Environment

Activate the virtual environment:

```bash
source venv/bin/activate
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

## Production Deployment

Production deploy runs only on the Oracle VM k3s cluster.

Use the documentation and deploy script:

- [Documentation index](docs/README.md)
- [Production deployment](docs/01-production-deployment.md)
- [AI engineering review](docs/04-ai-engineering-review.md)

```bash
bash DevOps/generate-images.sh --tag current
bash DevOps/k3s/deploy-to-vm.sh --image-tag current
```
