"""Prompt templates and static conversational copy for Citta Companion."""

from __future__ import annotations

from config import SUPPORTED_LANGUAGES

# ---------------------------------------------------------------------------
# System prompt for the wellbeing assistant
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """\
You are "Citta Companion", an empathetic employee wellbeing discovery assistant.

Your goal is to have a warm, supportive conversation that gently explores the
employee's wellbeing. You are speaking with an employee from the "{sector}"
sector. Respond in this language: {language}.

STRICT RULES — follow these at all times:
- Be warm, empathetic, non-judgemental and human.
- Ask ONLY ONE question at a time. Never stack multiple questions.
- Keep every response SHORT (2-4 sentences maximum).
- NEVER diagnose any condition.
- NEVER prescribe or suggest medication.
- NEVER claim to be a therapist, doctor or counsellor.
- Do not give clinical advice. You gather understanding, you do not treat.
- Reassure the employee that their employer will not see their personal answers.

NEVER INVENT SUPPORT RESOURCES. This is the most important rule here.
- Do NOT provide phone numbers, helplines, email addresses, links, portals, or
  the name of any support programme — not even as an example or a placeholder.
- Do NOT refer to an "Employee Assistance Programme" or "EAP". Citta has not
  given you any such details, so anything you produce would be invented, and an
  invented support number is worse than none: someone in distress may dial it.
- When a person asks for help or wants to speak to someone, say that you have
  noted their request and that Citta's wellbeing team will follow up with them
  directly. That is true — it is exactly what happens.
- The ONLY exception is the immediate-danger case, where you may say to contact
  local emergency services or attend the nearest hospital, without naming a
  specific number.

Over the course of the conversation, gently and naturally gather understanding
about the following areas (one topic at a time, only when it fits the flow):
- General wellbeing
- Stress and burnout
- Sleep and fatigue
- Workplace pressure
- Manager or team stress
- Coping strategies
- Emotional regulation
- Workplace conflict or psychological safety
- Whether they would like human support

Always acknowledge what the person shares before moving to the next gentle
question. If the person seems to be in distress, respond with compassion and
encourage them to reach out to a trusted person or professional support.
"""

# ---------------------------------------------------------------------------
# Summary generation prompt
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = """\
Based on the entire conversation above, produce a structured wellbeing summary.

Return ONLY valid JSON (no markdown, no code fences, no commentary) with EXACTLY
these keys:

{
  "overall_wellbeing": "<short assessment: good / fair / concerning / unclear>",
  "stress_level": "<low / moderate / high / unclear>",
  "sleep": "<short description of sleep quality>",
  "burnout": "<none / mild / moderate / severe / unclear>",
  "workplace_pressure": "<short description of workload/pressure>",
  "manager_relationship": "<short description>",
  "coping_strategy": "<how the person copes, if mentioned>",
  "emotional_regulation": "<how the person manages difficult emotions, if mentioned>",
  "human_support_requested": "<yes / no / unclear>",
  "sleep_quality": "<good / fair / poor / unclear>",
  "pressure_level": "<low / moderate / high / unclear>",
  "manager_support": "<supportive / mixed / unsupportive / unclear>",
  "coping_level": "<healthy / limited / none / unclear>",
  "conflict_level": "<none / some / significant / unclear>",
  "risk_category": "<green / yellow / amber / red / crisis>",
  "summary": "<2-3 sentence neutral narrative summary>",
  "recommendation": "<one short, non-clinical supportive recommendation>"
}

Do not invent details that were not discussed; use "unclear" where information
is missing. Never include personally identifying free text beyond what is needed.

FIVE FIELDS ARE PAIRED. Each of sleep_quality, pressure_level, manager_support,
coping_level and conflict_level is a graded version of a free-text field beside
it (sleep, workplace_pressure, manager_relationship, coping_strategy, and the
conflict discussed in the conversation).

The free text is read by Citta's intake team, so keep it specific. The graded
value is COUNTED on the employer's de-identified report, so it must come from
the fixed list and nothing else — never a phrase, never a sentence. If the
conversation did not cover it, the grade is "unclear"; do not infer a grade
from an absence.

Grade what the person described, not how calmly they described it. A person who
lightly mentions sleeping four hours has poor sleep.

Write every free-text value in ENGLISH, whatever language the conversation was
held in. Citta's intake team allocates cases from these fields and does not read
all seven languages.

RISK CATEGORY — apply these criteria literally. Judge what the person described,
never how calmly they described it, and never the language they used:

- "crisis": any mention of suicide, self-harm, harming others, abuse, domestic
  violence, or feeling unsafe. Always crisis, however briefly it was raised.
- "red": severe distress, hopelessness, being unable to function, or symptoms
  that sound like they need clinical attention soon.
- "amber": clear signs of burnout or sustained strain — for example persistent
  sleep loss (waking in the night, under six hours), emotional outbursts at
  home or work, bottling everything up, or an unmanageable long-term workload.
  ALSO amber, at minimum, whenever the person asks to speak to a human.
- "yellow": mild or emerging concern; manageable pressure with some coping.
- "green": generally coping, no significant concern raised.

If a conversation sits between two bands, choose the HIGHER one. Under-calling
risk leaves someone without support; over-calling it only costs a review.
"""

# ---------------------------------------------------------------------------
# Static conversational copy
# ---------------------------------------------------------------------------
# The opening message, per language. Everything the model says afterwards is
# generated in the employee's language, so an English-only greeting made the
# first screen the odd one out.
#
# ``note`` is the safety and privacy disclaimer. It is always shown in English
# as well as the employee's language: the English wording is the one agreed with
# Citta, and a translation — however careful — should not be the only version of
# a statement about what the employer does and does not receive.
#
# "Citta Companion" stays in Latin script everywhere: it is the product name,
# and it matches the sidebar and the invitation email.
WELCOME_COPY = {
    "en": {
        "hero": "Hello, I'm Citta Companion.",
        "lead": (
            "I'm here to support your wellbeing and help understand what kind of "
            "support may be useful."
        ),
        "note": (
            "This is not a diagnosis, therapy, or emergency service. Your employer "
            "will not receive your individual responses — they may only receive "
            "de-identified wellbeing themes."
        ),
        "question": "How are you feeling today?",
    },
    "hi": {
        "hero": "नमस्ते, मैं Citta Companion हूँ।",
        "lead": (
            "मैं आपकी भलाई में सहयोग करने और यह समझने में मदद करने के लिए यहाँ हूँ कि "
            "किस तरह का सहयोग उपयोगी हो सकता है।"
        ),
        "note": (
            "यह कोई निदान, थेरेपी या आपातकालीन सेवा नहीं है। आपके नियोक्ता को आपके "
            "व्यक्तिगत उत्तर नहीं मिलेंगे — उन्हें केवल पहचान रहित कल्याण विषय ही मिल सकते हैं।"
        ),
        "question": "आज आप कैसा महसूस कर रहे हैं?",
    },
    "kn": {
        "hero": "ನಮಸ್ಕಾರ, ನಾನು Citta Companion.",
        "lead": (
            "ನಿಮ್ಮ ಯೋಗಕ್ಷೇಮಕ್ಕೆ ಬೆಂಬಲ ನೀಡಲು ಮತ್ತು ಯಾವ ರೀತಿಯ ಬೆಂಬಲ ಉಪಯುಕ್ತವಾಗಬಹುದು "
            "ಎಂಬುದನ್ನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ನಾನು ಇಲ್ಲಿದ್ದೇನೆ."
        ),
        "note": (
            "ಇದು ರೋಗನಿರ್ಣಯ, ಚಿಕಿತ್ಸೆ ಅಥವಾ ತುರ್ತು ಸೇವೆಯಲ್ಲ. ನಿಮ್ಮ ವೈಯಕ್ತಿಕ ಉತ್ತರಗಳನ್ನು ನಿಮ್ಮ "
            "ಉದ್ಯೋಗದಾತರು ಪಡೆಯುವುದಿಲ್ಲ — ಅವರು ಗುರುತು ತೆಗೆದುಹಾಕಿದ ಯೋಗಕ್ಷೇಮ ವಿಷಯಗಳನ್ನು "
            "ಮಾತ್ರ ಪಡೆಯಬಹುದು."
        ),
        "question": "ಇಂದು ನಿಮಗೆ ಹೇಗೆ ಅನಿಸುತ್ತಿದೆ?",
    },
    "ta": {
        "hero": "வணக்கம், நான் Citta Companion.",
        "lead": (
            "உங்கள் நல்வாழ்வுக்கு உதவவும், எந்த வகையான ஆதரவு பயனுள்ளதாக இருக்கும் "
            "என்பதைப் புரிந்துகொள்ளவும் நான் இங்கே இருக்கிறேன்."
        ),
        "note": (
            "இது நோய் கண்டறிதல், சிகிச்சை அல்லது அவசர சேவை அல்ல. உங்கள் தனிப்பட்ட "
            "பதில்களை உங்கள் நிறுவனம் பெறாது — அடையாளம் நீக்கப்பட்ட நல்வாழ்வுக் "
            "கருப்பொருள்களை மட்டுமே அவர்கள் பெறலாம்."
        ),
        "question": "இன்று நீங்கள் எப்படி உணர்கிறீர்கள்?",
    },
    "te": {
        "hero": "నమస్కారం, నేను Citta Companion.",
        "lead": (
            "మీ శ్రేయస్సుకు తోడ్పడటానికి, ఎలాంటి మద్దతు ఉపయోగకరంగా ఉంటుందో "
            "అర్థం చేసుకోవడానికి నేను ఇక్కడ ఉన్నాను."
        ),
        "note": (
            "ఇది రోగ నిర్ధారణ, చికిత్స లేదా అత్యవసర సేవ కాదు. మీ వ్యక్తిగత సమాధానాలను "
            "మీ యజమాని అందుకోరు — వారు గుర్తింపు తొలగించిన శ్రేయస్సు అంశాలను మాత్రమే "
            "అందుకోవచ్చు."
        ),
        "question": "ఈ రోజు మీకు ఎలా అనిపిస్తోంది?",
    },
    "mr": {
        "hero": "नमस्कार, मी Citta Companion आहे.",
        "lead": (
            "तुमच्या स्वास्थ्याला आधार देण्यासाठी आणि कोणत्या प्रकारचा आधार उपयुक्त ठरेल "
            "हे समजून घेण्यासाठी मी येथे आहे."
        ),
        "note": (
            "ही निदान, थेरपी किंवा आपत्कालीन सेवा नाही. तुमची वैयक्तिक उत्तरे तुमच्या "
            "नियोक्त्याला मिळणार नाहीत — त्यांना फक्त ओळख काढून टाकलेले स्वास्थ्यविषयक "
            "मुद्दे मिळू शकतात."
        ),
        "question": "आज तुम्हाला कसे वाटत आहे?",
    },
    "bn": {
        "hero": "নমস্কার, আমি Citta Companion।",
        "lead": (
            "আপনার সুস্থতায় সহায়তা করতে এবং কোন ধরনের সহায়তা কাজে লাগতে পারে তা "
            "বুঝতে আমি এখানে আছি।"
        ),
        "note": (
            "এটি কোনো রোগনির্ণয়, থেরাপি বা জরুরি পরিষেবা নয়। আপনার ব্যক্তিগত উত্তর "
            "আপনার নিয়োগকর্তা পাবেন না — তাঁরা কেবল পরিচয়হীন সুস্থতা-বিষয়ক প্রবণতা "
            "পেতে পারেন।"
        ),
        "question": "আজ আপনার কেমন লাগছে?",
    },
}

# Interface copy the employee reads or clicks. The quick-reply chips are sent
# verbatim as the employee's first message, so they have to be in the language
# the conversation is being held in — an English "Workload" would open a Tamil
# conversation in English.
UI_COPY = {
    "en": {
        "chips": ["Workload", "Sleep", "Team pressure", "Something personal"],
        "finish": "Finish conversation",
        "placeholder": "Share how you're feeling…",
    },
    "hi": {
        "chips": ["काम का बोझ", "नींद", "टीम का दबाव", "कुछ निजी"],
        "finish": "बातचीत समाप्त करें",
        "placeholder": "आप कैसा महसूस कर रहे हैं, बताइए…",
    },
    "kn": {
        "chips": ["ಕೆಲಸದ ಹೊರೆ", "ನಿದ್ರೆ", "ತಂಡದ ಒತ್ತಡ", "ವೈಯಕ್ತಿಕ ವಿಷಯ"],
        "finish": "ಸಂಭಾಷಣೆ ಮುಗಿಸಿ",
        "placeholder": "ನಿಮಗೆ ಹೇಗೆ ಅನಿಸುತ್ತಿದೆ ಎಂದು ಹಂಚಿಕೊಳ್ಳಿ…",
    },
    "ta": {
        "chips": ["வேலைப்பளு", "தூக்கம்", "குழு அழுத்தம்", "தனிப்பட்ட விஷயம்"],
        "finish": "உரையாடலை முடிக்கவும்",
        "placeholder": "நீங்கள் எப்படி உணர்கிறீர்கள் என்பதைப் பகிருங்கள்…",
    },
    "te": {
        "chips": ["పని భారం", "నిద్ర", "బృంద ఒత్తిడి", "వ్యక్తిగత విషయం"],
        "finish": "సంభాషణ ముగించండి",
        "placeholder": "మీకు ఎలా అనిపిస్తోందో పంచుకోండి…",
    },
    "mr": {
        "chips": ["कामाचा भार", "झोप", "संघातील दबाव", "वैयक्तिक काही"],
        "finish": "संभाषण संपवा",
        "placeholder": "तुम्हाला कसे वाटत आहे ते सांगा…",
    },
    "bn": {
        "chips": ["কাজের চাপ", "ঘুম", "দলের চাপ", "ব্যক্তিগত কিছু"],
        "finish": "কথোপকথন শেষ করুন",
        "placeholder": "আপনার কেমন লাগছে তা জানান…",
    },
}

CRISIS_MESSAGE = (
    "**If you are at immediate risk of harm or feel unsafe, please contact local "
    "emergency services or attend the nearest hospital.**\n\n"
    "Citta Companion is not an emergency service."
)

FALLBACK_ERROR_MESSAGE = (
    "I'm having trouble responding right now. Please try again in a moment. "
    "If this keeps happening, you can still reach out to a trusted person or "
    "your local support services."
)


def get_system_prompt(sector: str, lang: str) -> str:
    """Build the system prompt for the given sector and language."""
    language = SUPPORTED_LANGUAGES.get(lang, "English")
    return SYSTEM_PROMPT_TEMPLATE.format(sector=sector or "General", language=language)


def get_welcome_copy(lang: str) -> dict:
    """Return the welcome copy for ``lang``, falling back to English.

    ``note_en`` carries the English disclaimer and is empty when the employee's
    language *is* English, so a renderer can print it unconditionally without
    showing the same sentence twice.
    """
    copy = dict(WELCOME_COPY.get(lang) or WELCOME_COPY["en"])
    copy["note_en"] = "" if copy["note"] == WELCOME_COPY["en"]["note"] else (
        WELCOME_COPY["en"]["note"]
    )
    return copy


def get_ui_copy(lang: str) -> dict:
    """Return the chip labels, finish label and composer hint for ``lang``."""
    return UI_COPY.get(lang) or UI_COPY["en"]


def get_welcome_message(lang: str) -> str:
    """The welcome copy as plain text, for the model history and transcripts."""
    copy = get_welcome_copy(lang)
    parts = [copy["hero"], copy["lead"], copy["note"], copy["note_en"], copy["question"]]
    return "\n\n".join(part for part in parts if part)
