"""A deliberately small Gita collection. Sanskrit is public-domain scripture.

Translations below are our plain-language renderings, not quoted translations.
Source links let the reader inspect the Sanskrit and compare interpretations.
Never use the model's recollection as a source for a quoted shlok.
"""

VERSES = {
    "2.47": {
        "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।\nमा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि।।",
        "english": "Your responsibility is to act, not to control the fruits of action. Do not make the result your only reason for acting, and do not become attached to inaction.",
        "hindi": "तुम्हारा अधिकार कर्म करने पर है, उसके फल को नियंत्रित करने पर नहीं। केवल फल के लिए कर्म मत करो, और कर्म न करने की ओर भी मत झुको।",
        "themes": "work effort outcomes anxiety responsibility action career",
    },
    "2.48": {
        "sanskrit": "योगस्थः कुरु कर्माणि सङ्गं त्यक्त्वा धनञ्जय।\nसिद्ध्यसिद्ध्योः समो भूत्वा समत्वं योग उच्यते।।",
        "english": "Act with inner steadiness, letting go of attachment. Meet success and failure with an even mind; this balance is called yoga.",
        "hindi": "मन को स्थिर रखकर और आसक्ति छोड़कर कर्म करो। सफलता और असफलता में संतुलित रहो; इसी समभाव को योग कहा गया है।",
        "themes": "success failure balance disappointment results steadiness",
    },
    "2.14": {
        "sanskrit": "मात्रास्पर्शास्तु कौन्तेय शीतोष्णसुखदुःखदाः।\nआगमापायिनोऽनित्यास्तांस्तितिक्षस्व भारत।।",
        "english": "Contact with the world brings cold and heat, pleasure and pain. These experiences come and go; learn to endure them with patience.",
        "hindi": "संसार के अनुभव सर्दी-गर्मी और सुख-दुःख लाते हैं। ये आते-जाते हैं, स्थायी नहीं हैं; इन्हें धैर्य से सहना सीखो।",
        "themes": "change discomfort loss grief feelings patience impermanence",
    },
    "6.5": {
        "sanskrit": "उद्धरेदात्मनात्मानं नात्मानमवसादयेत्।\nआत्मैव ह्यात्मनो बन्धुरात्मैव रिपुरात्मनः।।",
        "english": "Lift yourself through your own efforts; do not let yourself fall. You can be your own friend, and you can also be your own enemy.",
        "hindi": "अपने प्रयास से स्वयं को ऊपर उठाओ, स्वयं को गिरने मत दो। मनुष्य स्वयं अपना मित्र भी बन सकता है और अपना शत्रु भी।",
        "themes": "self criticism agency habits confidence shame growth friend mind",
    },
    "6.26": {
        "sanskrit": "यतो यतो निश्चरति मनश्चञ्चलमस्थिरम्।\nततस्ततो नियम्यैतदात्मन्येव वशं नयेत्।।",
        "english": "Whenever the restless mind wanders, gently bring it back and settle it within yourself.",
        "hindi": "यह चंचल और अस्थिर मन जहाँ-जहाँ भटके, वहाँ से उसे सँभालकर फिर अपने भीतर स्थिर करो।",
        "themes": "overthinking attention rumination restless meditation focus mind",
    },
    "12.13": {
        "sanskrit": "अद्वेष्टा सर्वभूतानां मैत्रः करुण एव च।\nनिर्ममो निरहङ्कारः समदुःखसुखः क्षमी।।",
        "english": "One who holds no hatred toward others, who is friendly and compassionate, free from possessiveness and pride, balanced in pain and joy, and forgiving—",
        "hindi": "जो किसी से द्वेष नहीं रखता, मैत्री और करुणा रखता है, ममता और अहंकार से मुक्त है, सुख-दुःख में संतुलित है और क्षमाशील है—",
        "themes": "compassion relationships resentment forgiveness ego kindness hatred",
        "note": "This verse continues in 12.14. Forgiveness does not require tolerating harm or abandoning boundaries.",
    },
}


def verse_payload(reference: str) -> dict | None:
    verse = VERSES.get(reference)
    if verse is None:
        return None
    chapter, number = reference.split(".")
    return {
        "reference": reference,
        "title": f"Bhagavad Gita {reference}",
        **verse,
        "source_url": f"https://www.gitasupersite.in/srimad?language=dv&field_chapter_value={chapter}&field_nsutra_value={number}",
        "translation_note": "Plain-language rendering by Saarthi; interpretations can differ.",
    }
