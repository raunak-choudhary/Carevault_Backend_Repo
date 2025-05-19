# CareVault Backend

CareVault is an AI-powered healthcare management platform that helps users manage medical documents, track appointments, and interact with an AI assistant for health-related queries using a RAG-based system.

This repository contains the **backend codebase** developed in Python, which includes the RESTful API, Supabase integration for storage and database management, and RAG system integration.  
To explore the UI and user experience, visit the frontend repository:  
[CareVault Frontend Repository](https://github.com/raunak-choudhary/Carevault_Frontend_Repo.git)

## System Architecture  
(Please check the Architecture Diagram in the Frontend Repository of Carevault)

- **Users** interact with the React frontend.
- The frontend communicates with a **Python backend** to handle data and AI requests.
- The backend interfaces with **Supabase**, which handles both file storage (via buckets) and structured data (via PostgreSQL).
- Uploaded **User Medical Documents** are accessed by a **RAG system**, enabling intelligent retrieval and responses based on the document content.

## Authors

- **Raunak Choudhary**  
  Master’s in Computer Science, NYU Tandon  
  [rc5553@nyu.edu](mailto:rc5553@nyu.edu)

- **Aninda Ghosh**  
  Master’s in Computer Science, NYU Tandon  
  [ag7762@nyu.edu](mailto:ag7762@nyu.edu)
