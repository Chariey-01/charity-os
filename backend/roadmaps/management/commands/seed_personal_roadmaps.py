from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planning.models import Area
from roadmaps.models import Roadmap, RoadmapNode, RoadmapResource


def guidance(purpose, outcome, how, evidence, completion):
    return "\n\n".join(
        (
            f"PURPOSE\n{purpose}",
            f"OUTCOME\n{outcome}",
            f"HOW TO WORK THIS TRACK\n{how}",
            f"EVIDENCE\n{evidence}",
            f"COMPLETION\n{completion}",
        )
    )


COMMON_EVIDENCE = "Use working artifacts, notes, tests, explanations, or shipped outcomes. Passive tutorial watching does not count."

ROADMAPS = [
    {
        "title": "Software Engineering",
        "area": "Software Engineering",
        "description": guidance(
            "Become a strong software engineer who can independently understand, design, build, test, debug and ship production-quality applications.",
            "Build and explain reliable applications end to end.",
            "Strengthen fundamentals; build real applications; practise architecture, debugging, tests, databases, APIs, Git, deployment, and project retrospectives.",
            "GitHub commits, pull requests, deployed applications, architecture notes, tests, technical explanations, and project case studies.",
            "I can independently take a production-quality change from understanding to shipped, tested outcome.",
        ),
        "sections": [
            (
                "Engineering fundamentals",
                [
                    "Programming fundamentals",
                    "Debugging deliberately",
                    "Databases and SQL",
                    "HTTP and APIs",
                    "Testing and quality",
                ],
            ),
            (
                "Build and ship",
                [
                    "Real application build",
                    "Architecture and system design",
                    "Git workflows",
                    "Deploy an application",
                    "Review and improve a previous project",
                ],
            ),
        ],
    },
    {
        "title": "TypeScript",
        "area": "Software Engineering",
        "description": guidance(
            "Move from JavaScript familiarity to confidently building strongly typed production React applications.",
            "I can build and explain a TypeScript React application without converting everything to any.",
            "For every topic: learn → practise → implement → explain → attach evidence. Use TypeScript substantially in a professional portfolio.",
            "Typed source, component tests, API types, explanations, and a portfolio project.",
            "A real React application is typed end to end and its important tradeoffs can be explained.",
        ),
        "sections": [
            (
                "Foundations",
                [
                    "Why TypeScript",
                    "Primitive types",
                    "Arrays and tuples",
                    "Objects",
                    "Functions",
                    "Optional and default parameters",
                ],
            ),
            (
                "Type system",
                [
                    "Type aliases",
                    "Interfaces",
                    "Unions and intersections",
                    "Literal types",
                    "Enums and alternatives",
                    "Narrowing and type guards",
                ],
            ),
            (
                "Intermediate",
                [
                    "Generics",
                    "keyof and typeof",
                    "Indexed access",
                    "Utility types",
                    "unknown versus any",
                    "never and assertions",
                ],
            ),
            (
                "Application development",
                [
                    "Typing API responses",
                    "Async functions",
                    "Errors",
                    "Forms",
                    "Reusable domain types",
                ],
            ),
            (
                "React + TypeScript",
                [
                    "Props",
                    "State and events",
                    "Hooks",
                    "Forms",
                    "Context",
                    "Reusable components and API clients",
                ],
            ),
            ("Testing", ["Typed tests", "Mocking", "Component tests"]),
            (
                "Project application",
                ["Build a professional TypeScript portfolio application"],
            ),
        ],
    },
    {
        "title": "Node.js",
        "area": "Software Engineering",
        "description": guidance(
            "Add a serious JavaScript/TypeScript backend stack alongside Python backend experience.",
            "I can design, build, test and deploy a Node.js backend API and explain its architecture.",
            "Build progressively with Node runtime fundamentals, HTTP, Express, PostgreSQL, security, tests, production configuration, logging, and graceful shutdown.",
            "A deployed Node/TypeScript API, tests, API documentation, architecture notes, and deployment evidence.",
            "At least one real Node/TypeScript API is built, tested, deployed, and explainable.",
        ),
        "sections": [
            (
                "Runtime fundamentals",
                [
                    "Node runtime",
                    "Modules and npm",
                    "package.json",
                    "Environment variables",
                    "Filesystem and streams",
                    "Events, async model, and event loop",
                ],
            ),
            (
                "Backend fundamentals",
                ["HTTP", "REST", "Routing and middleware", "Validation", "Errors"],
            ),
            ("Framework", ["Express application"]),
            (
                "Data",
                [
                    "PostgreSQL",
                    "Database access",
                    "Migrations",
                    "Relationships",
                    "Transactions",
                ],
            ),
            (
                "Security",
                [
                    "Authentication",
                    "Authorization",
                    "Password hashing",
                    "Input validation",
                    "Web vulnerabilities",
                    "Rate limiting concepts",
                ],
            ),
            (
                "Testing and production",
                [
                    "Unit, integration, and API tests",
                    "Logging and configuration",
                    "Deployment and graceful shutdown",
                    "Error monitoring concepts",
                ],
            ),
            ("Project", ["Build and deploy a real Node/TypeScript API"]),
        ],
    },
    {
        "title": "GitHub & Open Source",
        "area": "Software Engineering",
        "description": guidance(
            "Build genuine public engineering evidence and learn professional collaboration workflows.",
            "I have a professional GitHub profile and genuine contributions beyond only my own repositories.",
            "Let achievements follow real engineering activity; never manufacture commits, badges, or activity.",
            "GitHub issue, PR, repository, release, and contribution URLs.",
            "A clean professional profile and at least one genuine external contribution are visible.",
        ),
        "sections": [
            (
                "Git fundamentals",
                [
                    "Commits",
                    "Branches",
                    "Merges and rebasing",
                    "Resolve conflicts",
                    "Useful commit messages",
                ],
            ),
            (
                "GitHub workflow",
                [
                    "Issues",
                    "Feature branches",
                    "Pull requests and code review",
                    "Discussions",
                    "Releases, tags, and Actions",
                ],
            ),
            (
                "Profile",
                [
                    "Profile README",
                    "Pin strongest repositories",
                    "Project READMEs",
                    "Repository hygiene",
                ],
            ),
            (
                "Open source",
                [
                    "Find a beginner-friendly repository",
                    "Read contribution guidelines",
                    "Reproduce an issue",
                    "Discuss before large changes",
                    "Implement, test, open PR, respond to review",
                ],
            ),
            (
                "Genuine achievements",
                ["Record a GitHub achievement or badge I genuinely unlocked"],
            ),
        ],
    },
    {
        "title": "Jobs Club",
        "area": "Career",
        "description": guidance(
            "Turn technical ability into job readiness and employment opportunities.",
            "A complete, evidence-backed job-readiness system is ready for the exact Jobs Club curriculum.",
            "Use these categories as a container. Add the exact Jobs Club roadmap and material received later; no curriculum is invented here.",
            "Tailored CVs, profile links, portfolio case studies, mock interview feedback, and application outcomes.",
            "The supplied Jobs Club material is entered and each relevant deliverable is evidenced.",
        ),
        "sections": [
            (
                "Career identity",
                [
                    "Professional introduction",
                    "Career identity statement",
                    "Elevator pitch",
                ],
            ),
            (
                "CV",
                [
                    "Master CV",
                    "Frontend CV",
                    "Backend CV",
                    "Full-stack CV",
                    "Role tailoring",
                ],
            ),
            (
                "LinkedIn",
                ["Headline", "About", "Featured projects", "Experience", "Networking"],
            ),
            (
                "GitHub and portfolio",
                [
                    "Profile and pinned repositories",
                    "Professional portfolio",
                    "Project case studies",
                    "Deployment",
                ],
            ),
            (
                "Interview preparation",
                [
                    "Behavioural",
                    "Technical",
                    "Live coding",
                    "Project explanation",
                    "Mock interviews",
                ],
            ),
            (
                "Applications and networking",
                [
                    "Sourcing and tailoring",
                    "Applying and follow-up",
                    "Outcome tracking",
                    "Events, recruiters, developers, alumni, follow-ups",
                ],
            ),
        ],
    },
    {
        "title": "Interview Preparation",
        "area": "Career",
        "description": guidance(
            "Become comfortable demonstrating engineering ability under interview conditions.",
            "I can solve, explain, and reflect on technical and behavioural interview problems.",
            "Practise deliberately, explain tradeoffs aloud, and record feedback rather than only collecting solved exercises.",
            "Solutions, notes, mock interview reflections, scores, and feedback.",
            "For each major project I can explain problem, architecture, contribution, decision, failure, tradeoff, testing, deployment, and improvement.",
        ),
        "sections": [
            (
                "Coding fundamentals",
                [
                    "Arrays and strings",
                    "Objects and maps",
                    "Loops and recursion",
                    "Complexity",
                ],
            ),
            (
                "Data structures",
                ["Stacks and queues", "Linked lists", "Trees", "Graphs basics"],
            ),
            ("Algorithms", ["Searching", "Sorting", "Common patterns"]),
            (
                "Frontend interviews",
                [
                    "JavaScript",
                    "React",
                    "TypeScript",
                    "DOM and accessibility",
                    "State and effects",
                ],
            ),
            (
                "Backend interviews",
                [
                    "Python",
                    "Flask and Django",
                    "APIs and authentication",
                    "SQL and PostgreSQL",
                    "HTTP",
                ],
            ),
            (
                "Engineering and behavioural",
                [
                    "Debugging, testing, Git, architecture, security",
                    "STAR responses, teamwork, conflict, leadership, failure, learning",
                ],
            ),
            ("Project defence", ["Practise a complete project explanation"]),
        ],
    },
    {
        "title": "Career & Applications",
        "area": "Career",
        "description": guidance(
            "Run my job search as a measurable pipeline rather than random applications.",
            "I consistently source, evaluate, tailor, apply, follow up, interview, and learn from outcomes.",
            "Track fit, quality of evidence, follow-up, feedback, and learning—not application count alone.",
            "Role research, tailored materials, messages, interview notes, and outcomes.",
            "The pipeline is current and every meaningful opportunity has a next action or recorded outcome.",
        ),
        "sections": [
            (
                "Opportunity pipeline",
                [
                    "Source roles",
                    "Evaluate fit",
                    "Research company",
                    "Tailor CV and message",
                    "Apply",
                    "Follow up",
                    "Interview",
                    "Record outcome",
                    "Improve from feedback",
                ],
            )
        ],
    },
    {
        "title": "Computer Science Foundations",
        "area": "Computer Science",
        "description": guidance(
            "Strengthen foundations that bootcamp and project work may not cover deeply.",
            "Selected computer science foundations improve engineering decisions and explanations.",
            "Use selected Teach Yourself CS, OSSU, and reputable university material; prioritise what improves current engineering rather than recreating a degree checklist.",
            COMMON_EVIDENCE,
            "The selected foundation topics are understood well enough to apply and explain.",
        ),
        "sections": [
            (
                "Foundations",
                [
                    "Programming",
                    "Data structures and algorithms",
                    "Computer architecture",
                    "Operating systems",
                    "Networking",
                    "Databases",
                    "Distributed systems concepts",
                    "Security fundamentals",
                ],
            )
        ],
    },
    {
        "title": "AI Engineering",
        "area": "AI",
        "description": guidance(
            "Progress from software engineer using AI tools to an engineer who understands how AI-powered systems are designed and built.",
            "I can design responsible AI applications with evaluated, observable interfaces.",
            "Do not rush advanced AI before core engineering foundations; build small evaluated systems as concepts become useful.",
            "Experiments, evaluations, architecture notes, API integrations, and security reviews.",
            "A production-minded AI application can be explained from data and model behavior through deployment.",
        ),
        "sections": [
            (
                "Foundations",
                [
                    "AI and ML concepts",
                    "Python data stack",
                    "Data preparation",
                    "ML fundamentals",
                    "Model evaluation",
                ],
            ),
            (
                "LLM applications",
                [
                    "LLM concepts",
                    "Embeddings",
                    "APIs and structured outputs",
                    "RAG concepts",
                    "Evaluation",
                    "AI application architecture",
                ],
            ),
            (
                "Production",
                ["Responsible and security considerations", "Production AI systems"],
            ),
        ],
    },
    {
        "title": "Freelancing",
        "area": "Freelancing",
        "description": guidance(
            "Learn how to convert engineering ability into legitimate paid client work.",
            "I can scope, propose, deliver, and hand over a client project professionally.",
            "Start with a clear service, qualify the need, scope honestly, communicate clearly, and retain evidence of outcomes.",
            "Proposals, scopes, project plans, delivered work, handovers, testimonials, and referrals.",
            "A repeatable ethical client-work process exists from discovery through handover.",
        ),
        "sections": [
            (
                "Service and discovery",
                [
                    "Service definition",
                    "Positioning",
                    "Client discovery",
                    "Requirements gathering",
                    "Scoping and estimation",
                ],
            ),
            (
                "Delivery",
                [
                    "Proposals",
                    "Pricing concepts",
                    "Contracts and invoicing concepts",
                    "Communication",
                    "Delivery and revisions",
                    "Handover",
                    "Testimonials and referrals",
                ],
            ),
            ("Resource", ["Review the Truehost Kenya freelancing resource"]),
        ],
    },
    {
        "title": "Projects",
        "area": "Projects",
        "description": guidance(
            "Build fewer but stronger production-quality projects.",
            "Each serious project has a tested, deployed, documented story and a retrospective.",
            "Move through problem → requirements → architecture → implementation → tests → deployment → documentation → feedback → retrospective → case study.",
            "Repository, tests, deployment, README, user feedback, retrospective, and case study.",
            "A project is complete when another person can understand, run, evaluate, and learn from it.",
        ),
        "sections": [
            (
                "Project portfolio",
                [
                    "CharityOS",
                    "Professional portfolio",
                    "CampusPulse",
                    "DevCrypt",
                    "Send It",
                ],
            ),
            (
                "Project lifecycle",
                [
                    "Problem and requirements",
                    "Architecture and implementation",
                    "Tests and deployment",
                    "Documentation and user feedback",
                    "Retrospective and case study",
                ],
            ),
        ],
    },
    {
        "title": "Exercise",
        "area": "Exercise",
        "description": guidance(
            "Build sustainable physical consistency that supports energy and long-term work capacity.",
            "I consistently perform and log appropriate running, strength, mobility, and recovery work.",
            "Prefer weekly consistency over extreme daily targets. Sunday is the preferred rest day. Completion means performing or logging the session, not arbitrary focus time.",
            "Exercise logs, short reflections, and consistent weekly records.",
            "The routine is sustainable and evidenced over weeks, with Sunday protected as rest where possible.",
        ),
        "sections": [("Movement", ["Running", "Strength", "Mobility", "Recovery"])],
    },
    {
        "title": "Recovery",
        "area": "Recovery",
        "description": guidance(
            "Protect the capacity needed to sustain learning, employment preparation, projects, and exercise.",
            "Workload, sleep, rest, and reflection support sustainable progress.",
            "Track sleep consistency, rest, breaks, workload awareness, and weekly reflection. Never trade away sleep to inflate work metrics.",
            "Sleep records, weekly reviews, and honest workload notes.",
            "Recovery is treated as an input to sustainable work, not a score to game.",
        ),
        "sections": [
            (
                "Sustainable capacity",
                [
                    "Sleep consistency",
                    "Rest",
                    "Breaks",
                    "Workload awareness",
                    "Weekly reflection",
                ],
            )
        ],
    },
]


class Command(BaseCommand):
    help = "Seed personal development roadmaps for one existing user, without overwriting data."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(email__iexact=options["email"]).first()
        if not user:
            raise CommandError("User not found; create a user first.")
        created = skipped = nodes = 0
        for definition in ROADMAPS:
            roadmap, made = Roadmap.objects.get_or_create(
                user=user,
                title=definition["title"],
                defaults={
                    "description": definition["description"],
                    "status": Roadmap.Status.ACTIVE,
                    "area": Area.objects.filter(
                        user=user, name=definition["area"]
                    ).first(),
                },
            )
            if not made:
                skipped += 1
                continue
            created += 1
            for section_position, (section_title, items) in enumerate(
                definition["sections"]
            ):
                section = RoadmapNode.objects.create(
                    user=user,
                    roadmap=roadmap,
                    title=section_title,
                    description=f"Work through these topics by learning, practising, implementing, explaining, and attaching evidence. {COMMON_EVIDENCE}",
                    node_type=RoadmapNode.NodeType.SECTION,
                    position=section_position,
                )
                for item_position, item_title in enumerate(items):
                    RoadmapNode.objects.create(
                        user=user,
                        roadmap=roadmap,
                        parent=section,
                        title=item_title,
                        description=f"Next action: make this concrete with a small practice or artifact. {COMMON_EVIDENCE}",
                        node_type=RoadmapNode.NodeType.ITEM,
                        position=item_position,
                    )
                    nodes += 1
            if definition["title"] == "Freelancing":
                resource_node = roadmap.nodes.filter(
                    title="Review the Truehost Kenya freelancing resource"
                ).first()
                RoadmapResource.objects.create(
                    user=user,
                    node=resource_node,
                    label="Truehost Kenya",
                    url="https://truehost.co.ke/",
                    position=0,
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} roadmaps, {nodes} eligible items; skipped {skipped} existing roadmaps."
            )
        )
