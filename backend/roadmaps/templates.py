"""Starter roadmap templates.

A template is only a starting structure. Creating a roadmap from one copies
it into the user's own records, where every stage, item and resource can be
edited, reordered, archived or replaced. Everything starts as planned: a
template never records progress, completion or course enrolment.

The suggested resources are well-known free or official starting points.
The user adds their own (Udemy, freeCodeCamp, Microsoft Learn, docs, GitHub).
"""

from django.db import transaction

from .models import Roadmap, RoadmapNode, RoadmapResource

R = RoadmapResource.Kind


def stage(title, purpose, topics, practice, build, criteria, resources=()):
    return {
        "title": title,
        "purpose": purpose,
        "topics": topics,
        "practice": practice,
        "build": build,
        "criteria": criteria,
        "resources": resources,
    }


AI_ENGINEERING = {
    "key": "ai-engineering",
    "title": "AI Engineering",
    "summary": "From Python foundations to production AI systems, in 16 stages.",
    "description": (
        "A path from learning concepts to building production-quality AI "
        "applications. Each stage ends with something built and explained, "
        "not with a video watched."
    ),
    "purpose": (
        "Become an AI engineer who can design, build, evaluate and ship "
        "reliable AI applications."
    ),
    "stages": [
        stage(
            "Python foundations and software engineering",
            "Write clean, tested Python and work like an engineer.",
            ["Data structures, functions and modules", "Typing, packaging and virtual environments", "Testing with pytest", "Git, code review and debugging"],
            "Solve 10 small problems with tests first.",
            "A command-line tool with tests, a README and CI.",
            "I can build, test and publish a small Python package without a tutorial.",
            [("Python tutorial (official)", "https://docs.python.org/3/tutorial/", R.DOCS), ("pytest documentation", "https://docs.pytest.org/", R.DOCS)],
        ),
        stage(
            "Mathematics for machine learning",
            "Understand the maths that models are built on.",
            ["Linear algebra: vectors, matrices, dot products", "Calculus: derivatives and gradients", "Probability and statistics", "Optimisation and gradient descent"],
            "Implement gradient descent from scratch with NumPy.",
            "A notebook that explains linear regression from first principles.",
            "I can derive and explain the gradient of a simple loss function.",
            [("Mathematics for Machine Learning (book)", "https://mml-book.github.io/", R.BOOK)],
        ),
        stage(
            "Data analysis and manipulation",
            "Load, clean, explore and visualise real data.",
            ["NumPy arrays", "pandas DataFrames", "Cleaning and feature engineering", "Visualisation"],
            "Clean and analyse a public dataset end to end.",
            "A published data analysis with clear findings.",
            "I can turn a messy dataset into a clear, reproducible analysis.",
            [("pandas user guide", "https://pandas.pydata.org/docs/user_guide/index.html", R.DOCS), ("NumPy for absolute beginners", "https://numpy.org/doc/stable/user/absolute_beginners.html", R.DOCS)],
        ),
        stage(
            "Machine learning fundamentals",
            "Train, validate and compare classical models.",
            ["Supervised and unsupervised learning", "Train, validation and test splits", "Overfitting and regularisation", "Metrics and model selection"],
            "Compare three models on one dataset with cross-validation.",
            "A small predictive model served behind an API.",
            "I can explain why a model generalises or does not, using metrics.",
            [("scikit-learn user guide", "https://scikit-learn.org/stable/user_guide.html", R.DOCS), ("Google Machine Learning Crash Course", "https://developers.google.com/machine-learning/crash-course", R.COURSE)],
        ),
        stage(
            "Deep learning",
            "Understand how deep networks learn representations.",
            ["Perceptrons and multilayer networks", "Activation and loss functions", "Convolutional networks", "Regularisation for deep models"],
            "Train an image classifier and analyse its errors.",
            "A deep learning model with a written error analysis.",
            "I can explain what each layer and hyperparameter in my model does.",
            [("Practical Deep Learning (fast.ai)", "https://course.fast.ai/", R.COURSE), ("Deep Learning (book)", "https://www.deeplearningbook.org/", R.BOOK)],
        ),
        stage(
            "Neural networks and model training",
            "Build and train networks yourself in PyTorch.",
            ["Tensors and autograd", "Training loops", "Batching, learning rates and schedulers", "Checkpointing and reproducibility"],
            "Write a training loop from scratch without a high-level trainer.",
            "A small language model trained on your own text.",
            "I can debug a training run that does not converge.",
            [("PyTorch tutorials", "https://pytorch.org/tutorials/", R.DOCS), ("Neural Networks: Zero to Hero", "https://karpathy.ai/zero-to-hero.html", R.VIDEO)],
        ),
        stage(
            "Natural language processing",
            "Represent and process text.",
            ["Tokenisation", "Word embeddings", "Sequence models", "Classic NLP tasks: classification, NER, summarisation"],
            "Fine-tune a small text classifier.",
            "A text classification service for a real use case.",
            "I can choose and justify an NLP approach for a given problem.",
            [("Hugging Face Learn", "https://huggingface.co/learn", R.COURSE)],
        ),
        stage(
            "Transformers and large language models",
            "Understand how modern LLMs work and behave.",
            ["Attention and the transformer architecture", "Pre-training and fine-tuning", "Prompting and context windows", "Limitations: hallucination, bias, cost"],
            "Implement scaled dot-product attention.",
            "A written explainer of how an LLM produces an answer.",
            "I can explain attention and the trade-offs of using an LLM.",
            [("Attention Is All You Need", "https://arxiv.org/abs/1706.03762", R.ARTICLE), ("Transformers documentation", "https://huggingface.co/docs/transformers/index", R.DOCS)],
        ),
        stage(
            "Embeddings and vector databases",
            "Search by meaning.",
            ["Sentence embeddings", "Similarity measures", "Vector indexes", "pgvector and hosted vector stores"],
            "Build semantic search over your own notes.",
            "A semantic search service on PostgreSQL with pgvector.",
            "I can choose an embedding model and index, and measure search quality.",
            [("Sentence Transformers", "https://www.sbert.net/", R.DOCS), ("pgvector", "https://github.com/pgvector/pgvector", R.REPO)],
        ),
        stage(
            "Retrieval-Augmented Generation",
            "Ground model answers in your own data.",
            ["Chunking strategies", "Retrieval and re-ranking", "Citations and grounding", "Failure modes of RAG"],
            "Compare two chunking strategies on the same questions.",
            "A RAG assistant over a real document set, with citations.",
            "My RAG system cites its sources and I can measure its accuracy.",
            [("Retrieval-Augmented Generation (paper)", "https://arxiv.org/abs/2005.11401", R.ARTICLE)],
        ),
        stage(
            "AI agents and tool use",
            "Let models act through tools safely.",
            ["Tool and function calling", "Agent loops and planning", "Model Context Protocol", "Guardrails and human approval"],
            "Give a model two tools and log every call it makes.",
            "An agent that completes a real multi-step task with approval steps.",
            "I can design an agent whose actions are bounded, logged and reviewable.",
            [("Model Context Protocol", "https://modelcontextprotocol.io/", R.DOCS)],
        ),
        stage(
            "Model evaluation and testing",
            "Know whether your AI system works.",
            ["Evaluation datasets", "Automated and model-graded evals", "Regression testing for prompts", "Human review"],
            "Write an eval set of 30 cases for one of your projects.",
            "An evaluation harness that runs in CI.",
            "Every change to my AI app is measured against an eval set.",
            [("OpenAI Evals", "https://github.com/openai/evals", R.REPO)],
        ),
        stage(
            "LLM application architecture",
            "Design AI features that are reliable and affordable.",
            ["Prompt and context management", "Caching, streaming and retries", "Cost and latency budgets", "Security: prompt injection and data privacy"],
            "Add caching and retries to an existing LLM feature.",
            "An architecture document for a production LLM feature.",
            "I can design an LLM feature with clear cost, latency and safety limits.",
            [("The Twelve-Factor App", "https://12factor.net/", R.ARTICLE)],
        ),
        stage(
            "AI APIs and deployment",
            "Ship AI features to real users.",
            ["Serving models and calling hosted APIs", "FastAPI or Django services", "Containers", "Secrets and configuration"],
            "Deploy a model-backed endpoint with authentication.",
            "A deployed AI web app with a public URL.",
            "I can deploy, secure and monitor an AI service.",
            [("FastAPI", "https://fastapi.tiangolo.com/", R.DOCS), ("Docker: get started", "https://docs.docker.com/get-started/", R.DOCS)],
        ),
        stage(
            "MLOps and production AI systems",
            "Run AI systems reliably over time.",
            ["Experiment tracking", "Model and data versioning", "Monitoring and drift", "Incident response"],
            "Track three experiments and compare them.",
            "A monitored AI service with an alert and a runbook.",
            "I can operate an AI system and respond when it degrades.",
            [("MLflow documentation", "https://mlflow.org/docs/latest/index.html", R.DOCS), ("Made With ML", "https://madewithml.com/", R.COURSE)],
        ),
        stage(
            "Portfolio projects and practical applications",
            "Prove the skills with shipped work.",
            ["Choose problems worth solving", "Write case studies", "Open-source contributions", "Present your work"],
            "Write a case study for one finished project.",
            "Three portfolio projects, each deployed, tested and written up.",
            "Someone can review my portfolio and see production-quality AI work.",
            [("GitHub Pages", "https://pages.github.com/", R.DOCS)],
        ),
    ],
}

TEMPLATES = {AI_ENGINEERING["key"]: AI_ENGINEERING}


def catalog():
    return [
        {
            "key": template["key"],
            "title": template["title"],
            "summary": template["summary"],
            "stages": [s["title"] for s in template["stages"]],
        }
        for template in TEMPLATES.values()
    ]


@transaction.atomic
def create_from_template(*, user, key, title=None, area=None, goal=None):
    template = TEMPLATES[key]
    roadmap = Roadmap.objects.create(
        user=user,
        title=(title or template["title"])[:160],
        description=template["description"],
        purpose=template["purpose"],
        area=area,
        goal=goal,
    )
    for position, spec in enumerate(template["stages"]):
        section = RoadmapNode.objects.create(
            user=user,
            roadmap=roadmap,
            title=f"{position + 1}. {spec['title']}",
            description=spec["purpose"],
            completion_criteria=spec["criteria"],
            node_type=RoadmapNode.NodeType.SECTION,
            position=position,
        )
        items = [
            *(("Learn: " + topic) for topic in spec["topics"]),
            "Practise: " + spec["practice"],
            "Build: " + spec["build"],
        ]
        for item_position, item_title in enumerate(items):
            RoadmapNode.objects.create(
                user=user,
                roadmap=roadmap,
                parent=section,
                title=item_title[:180],
                node_type=RoadmapNode.NodeType.ITEM,
                position=item_position,
            )
        for resource_position, (label, url, kind) in enumerate(spec["resources"]):
            RoadmapResource.objects.create(
                user=user,
                node=section,
                label=label,
                url=url,
                kind=kind,
                notes="Suggested starting point. Replace it with your own choice.",
                position=resource_position,
            )
    return roadmap
