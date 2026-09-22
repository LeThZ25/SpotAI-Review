# **PROJECT REQUIREMENTS Course: Software Engineering** 

## **1. General Information** 

|**Item**|**Requirement**|
|---|---|
|Project title|Modern and Intelligent Software Development Topics|
|Group size|2-3-4 students per group. Every member must take part in implementation and<br>present one part (see criterion “Participation in implementation”).|
|Number of topics|6 topics. Each group selects one topic; no two groups may choose the same<br>topic. Students may propose their own topic, subject to supervisor approval.|
|Related course content|Topics 1–12 of the course (especially Topics 2, 4, 5, 6, 7, 9, 10, 11, 12).|
|Required tools|Git/GitHub (source code management, commit history, issues, pull requests); a<br>task management tool (Trello, Jira or GitHub Projects).|
|Report standard|Use the “Project Report — Template” provided; Times New Roman 12 pt; line<br>spacing 1.3; page numbers.|
|Language|English for the report and presentation slides.|



## **2. Project Objectives** 

The project helps students apply software development processes, methods and tools to build a product that uses artificial intelligence or other modern techniques. After completing the project, students will be able to: 

- Apply software engineering principles at each stage of the development/maintenance process. 

- Analyze and select processes, methods, tools and development environments suited to technology trends. 

- Comply with standards and regulations in project planning and product quality evaluation. 

- Apply in-depth SE knowledge to carry out a development/maintenance project following a defined software process. 

- Collaborate with small and medium-sized teams. 

## **3. General Product Requirements** 

- The product must run (live demo or a screen-recorded video with narration). 

- It must have at least 3 core features defined in the topic and at least 1 feature that uses intelligent techniques (AI, machine learning, NLP, data analysis or data-driven automation). 

- Deliverables must include requirements documentation, architecture design (at least one UML or architecture diagram), a project plan (WBS, Gantt chart …) and a test report. 

- Source code must be published on GitHub with a README explaining installation and execution. The commit history must show each member’s contribution. 

- Technology choices must be justified, including trade-offs. Copying large blocks of code from other sources without citation and license information is not allowed. 

- Any use of AI coding assistants must be declared in the report appendix, stating the tool used and the parts it supported. 

## **4. Project Topics** 

Each topic includes: objectives, problem description, minimum functional requirements, suggested technologies and expected deliverables. Groups may extend a topic but must not reduce the minimum requirements. 

### **Topic 1 — Requirements Analysis Assistant Using Natural Language Processing** 

**Related topics:** Topic 6 (Requirements engineering), Topic 3 (Modeling) 

**Objective:** Build a tool that helps business analysts and requirements engineers: it reads naturallanguage business descriptions and automatically detects, classifies and improves requirements. 

**Problem description:** Users upload a business description document (in English or Vietnamese). The system splits the text into requirements, classifies them as functional or non-functional, flags ambiguous wording (for example “fast” or “user-friendly”), and generates user stories with acceptance criteria. 

### **Minimum functional requirements:** 

- Accept a document (text or .txt/.docx file) and extract a list of requirements. 

- Classify requirements as FR or NFR (a simple machine learning model or an LLM API). 

- Detect and highlight ambiguous terms, missing actors or missing measurable criteria. 

- Generate user stories in the form “As a <role>, I want <goal>, so that <benefit>” with acceptance criteria. 

- Export a condensed SRS and the corresponding Use Case diagram. 

**Suggested technologies:** Python (spaCy/NLTK or an LLM API), Flask/FastAPI or Streamlit; PlantUML for diagrams. 

**Expected deliverables:** Working demo application; condensed SRS document; classification accuracy report on at least 30 manually labelled requirements. 

### **Topic 2 — Agile Project Management System with Delivery Forecasting** 

**Related topics:** Topic 2 (Processes, TDD/Agile), Topic 5 (Project management, estimation) 

**Objective:** Build a sprint and backlog management tool that forecasts delivery using the team’s historical data. 

**Problem description:** The system manages product backlog, sprints and tasks following Scrum or Kanban. Using data from previous sprints (story points, completion time, defect counts), it suggests story points for new tasks and forecasts the release completion date based on velocity. 

### **Minimum functional requirements:** 

- Manage product backlog, sprints and tasks with statuses (To Do / In Progress / Done) and assignees. 

- Calculate Agile metrics: velocity, lead time and burndown chart. 

- Suggest story points for new tasks from historical data (regression or k-NN), or support Planning Poker sessions. 

- Forecast the release completion date with a confidence interval (for example, Monte Carlo simulation). 

- Provide login and role-based access (Product Owner, Scrum Master, Developer). 

**Suggested technologies:** Web application (React/Angular with Django or Node.js); PostgreSQL or Firebase; scikit-learn or a Monte Carlo library; optional integration with GitHub Projects or Jira. 

**Expected deliverables:** Working demo; sample sprint report; comparison of forecast error before and after applying the model. 

### **Topic 3 — Microservices-Based Online Learning Platform with an AI Assistant (RAG)** 

**Related topics:** Topic 7 (Architecture and design patterns), Topic 12 (Cloud-native, microservices) 

**Objective:** Design and build an online learning platform using a microservices architecture, integrated with a chatbot that answers questions based on course materials. 

**Problem description:** The platform includes services for user management, courses, content and an AI assistant. The assistant uses Retrieval-Augmented Generation (RAG) to answer student questions from lecture documents and cites its sources. 

### **Minimum functional requirements:** 

- Design a microservices architecture with at least 3 independent services and an API gateway. Explain the use of at least 2 design patterns (for example Gateway, Repository, Observer or Strategy). 

- Chatbot service: ingest documents (PDF/DOCX), split them into chunks, create embeddings, store them in a vector store and retrieve relevant passages. 

- Chatbot answers must include source citations (document name and page or section). 

- Package services with Docker and run them with docker-compose. 

- Include at least one answer-quality evaluation (for example, 20 questions with reference answers). 

**Suggested technologies:** Python/FastAPI or Node.js; Docker and docker-compose; vector store (FAISS or Chroma); LLM API or an open-source model. 

**Expected deliverables:** Architecture diagram (C4 or component diagram); source code and docker-compose file; answer-quality evaluation report. 

### **Topic 4 — Static Code Analysis and Code Review Tool with AI Support** 

**Related topics:** Topic 8 (Programming, debugging, source code management), Topic 10 (Refactoring and code review) 

**Objective:** Build a tool that automatically detects bugs and code smells and proposes refactoring, integrated into the pull request workflow. 

**Problem description:** The tool takes a code repository (Java or Python), runs static analysis to detect code smells, high complexity and duplicated code, then uses a language model to suggest refactorings. Results are posted as comments on pull requests. 

### **Minimum functional requirements:** 

- Static analysis that detects at least 5 code smell types (for example Long Method, Duplicated Code, Large Class) and calculates cyclomatic complexity. 

- Duplicate code detection (clone detection) with a configurable threshold. 

- AI-generated refactoring suggestions for each issue, with reasons and stated limitations. 

- GitHub Actions integration: the tool runs on each pull request and publishes the report. 

- Evaluation on at least 2 sample repositories, measuring precision of warnings through manual review. 

**Suggested technologies:** Java (PMD, SpotBugs, JavaParser) or Python (pylint, radon, ast); GitHub Actions; LLM API for refactoring suggestions. 

**Expected deliverables:** Tool runnable from the command line and GitHub Actions; results on two sample repositories; before/after refactoring examples. 

**Topic 5 — Automated Test Generation and Test Optimization System** 

**Related topics:** Topic 9 (Software testing), Topic 4 (Testing tools) 

**Objective:** Build a tool that supports test planning, generates test cases automatically and prioritizes test execution based on defect history. 

**Problem description:** The system is applied to a sample application (for example, an order management or booking system). It generates test cases from specifications (decision tables, equivalence partitioning, boundary values), runs unit and UI tests, and ranks test cases by risk. 

### **Minimum functional requirements:** 

- Apply at least 3 test design techniques: equivalence partitioning, boundary value analysis and decision tables. 

- Automatically generate unit tests (JUnit or pytest) from input specifications or with an AI model, with a human review step. 

- Automated UI tests for at least 3 business workflows (Selenium, Playwright or Cypress). 

- Prioritize test execution by defect history or code change (test prioritization). 

- Measure code coverage (line and branch) and report results using a Test Report template. 

**Suggested technologies:** Java (JUnit, Maven) or Python (pytest); Selenium or Playwright; JaCoCo or coverage.py; GitHub Actions. 

**Expected deliverables:** Re-runnable test suite; test plan and results report; coverage charts before and after optimization. 

### **Topic 6 — Green Software Monitoring Dashboard for Energy and Carbon Footprint** 

**Related topics:** Topic 12 (Green software, cloud-native), Topic 11 (Operation monitoring, maintenance) 

**Objective:** Build a dashboard that measures the energy use and estimated carbon footprint of a web service and recommends changes that reduce its resource consumption. 

**Problem description:** A sample web service (for example, a course catalogue API with a database) is instrumented to collect CPU, memory and request metrics. The system converts these metrics into estimated energy use and CO2 emissions, shows trends on a dashboard, and flags inefficient endpoints with suggested optimizations such as caching or query tuning. 

### **Minimum functional requirements:** 

- Instrument a sample service to collect CPU, memory, request count and response time metrics. 

- Estimate energy consumption and CO2 emissions from the metrics, with the estimation method and assumptions documented. 

- Dashboard showing usage trends over time, per service and per endpoint, with alert thresholds. 

- Detect at least 3 inefficiency patterns (for example, N+1 queries, missing cache, oversized responses) and recommend a fix for each. 

- Before-and-after experiment shows the measured reduction after applying at least 2 optimizations. 

**Suggested technologies:** Python or Node.js service; Prometheus and Grafana (or a lightweight dashboard framework); CodeCarbon or a documented power model; Docker for reproducible load tests. 

**Expected deliverables:** Running monitoring stack with dashboard; estimation method document; before/after measurement report with charts. 

## **5. Schedule and Milestones** 

|**Week/Class**|**Activity / Submission**|**Notes**|
|---|---|---|
|Week 4|Assign|The supervisor assign<br>project|
|Week 6 or 7<br>(depending on<br>scheduled)|Report 1: topic proposal (chosen topic, group name, initial<br>task allocation, objectives, scope, planned technologies,<br>analysis and design).|The supervisor reviews it<br>and may request<br>revisions.|
|Week 11 or 12<br>(depending on<br>scheduled)|Report 2: progress against plan (code+test), draft report.|Progress is assessed;<br>groups receive feedback<br>before final submission.|
|End of course|Final presentation: report (.docx and .pdf), slides, GitHub<br>link and demo video if required.|Group presentation,<br>demo and Q&A.|



## **6. Assessment Guidelines** 

|**Criterion**|**Weight**|**Excellent (8.5–10)**|**Good (7.0–8.4)**|**Average (5.5–**<br>**6.9)**|**Below**<br>**average (4.0–**<br>**5.4)**|**Poor (0–3.9)**|
|---|---|---|---|---|---|---|
|Report format|10%|Follows template,<br>clear, no spelling<br>errors|Follows<br>template, clear,<br>fewer than 10<br>errors|Clear, 11–20<br>errors|Unclear, over<br>20 errors|Poorly<br>formatted, very<br>many errors|
|Report content|40%|Meets 90–100% of<br>requirements;<br>extensions; full<br>citations|Meets 80–90%;<br>extensions;<br>incomplete<br>citations|Meets 70–80%|Meets<br>50–<br>60%|Meets less than<br>50%|
|Presentation skills|10%|Clear, confident,<br>persuasive;<br>engages audience<br>well|Clear,<br>confident;<br>engages<br>audience|Clear;<br>little<br>audience<br>interaction|Unclear, lacks<br>confidence|Speaks quietly;<br>no interaction|
|Answering<br>questions|20%|Answer<br>all<br>questions correctly|More than 2/3<br>correct|More than 1/2<br>correct|More than 1/3<br>correct|Less than 1/3<br>correct|
|Participation in<br>implementation|20%|100% of members<br>participate|About 80% of<br>members|About 60% of<br>members|50%<br>of<br>members|Less than 50%<br>of members|



## **7. Grouping** 

|**St**<br>**t**|**Mã Sinh viên**|**Họ và Tên**|**Grou**<br>**p N.o**|**Project name**|
|---|---|---|---|---|
|1|DTC23534000<br>1|Phạm Nguyên An||Green Software Monitoring|
|2|DTC23520079<br>8|Ma Đình Tuấn|1|<br>Dashboard for Energy and<br>|
|3|DTC23528006<br>2|Bùi Thu Hương||Carbon Footprint|
|4|DTC23521000<br>9|Hoàng Mạnh Cường||Rit<br>Ali|
||DTC23534000|||equremens<br>nayss|
|5|7|Lưu Thế Hà|2|Assistant<br>Using<br>Natural<br>|
|6|DTC23521002<br>6|Nguyễn Trần Anh Hoàng||Language Processing|
|7|DTC23521006<br>9|Phạm Hồng Ngọc Kiên|||
|8|DTC23521004<br>4|Mạc Minh Quang|3|Agile Project Management<br>System<br>with<br>Delivery<br>|
|9|DTC23520072<br>0|Nguyễn Thạc Thịnh||Forecasting|
|10|DTC23534003<br>0|Dương Lê Thưởng|4|Static Code Analysis and Code|
|11|DTC23521005<br>5|Dương Quốc Toản||Review Tool with AI Support|
|12|DTC23534002<br>6|Trần Thị Huyền Trang|||
|13|DTC23521005<br>7|Nguyễn Thành Trung|5|Automated Test Generation and<br>Test Optimization System|
|14|DTC23521002<br>4|Nguyễn Đại Hoàng|||
|15|DTC23034000<br>2|Akinyooye<br>Michelle<br>Taiwo<br>Aomide||Microservices-Based Online|
|16|DTC23034000<br>3|y<br>Chapoterera Shanea|6|Learning Platform with an AI<br>Assistant (RAG)|



