"""
BugExplanation dataclass and knowledge registry - Phase-07.
REIMPLEMENTED-2026

Frozen dataclass for bug explanations with bilingual support.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from python.phase07_knowledge.bug_types import BugType
from python.phase07_knowledge.knowledge_sources import KnowledgeSource


@dataclass(frozen=True)
class BugExplanation:
    """
    Frozen dataclass for bug explanations.
    
    All explanations include both English and Hindi versions.
    """
    bug_type: BugType
    title_en: str
    title_hi: str
    description_en: str
    description_hi: str
    impact_en: str
    impact_hi: str
    steps_en: Tuple[str, ...]
    steps_hi: Tuple[str, ...]
    cwe_id: Optional[str]
    source: KnowledgeSource


# Knowledge registry - explicit definitions only
_KNOWLEDGE_REGISTRY: Dict[BugType, BugExplanation] = {
    BugType.XSS: BugExplanation(
        bug_type=BugType.XSS,
        title_en="Cross-Site Scripting (XSS)",
        title_hi="क्रॉस-साइट स्क्रिप्टिंग (XSS)",
        description_en="A vulnerability that allows attackers to inject malicious scripts into web pages viewed by other users.",
        description_hi="एक कमजोरी जो हमलावरों को अन्य उपयोगकर्ताओं द्वारा देखे गए वेब पेजों में दुर्भावनापूर्ण स्क्रिप्ट इंजेक्ट करने की अनुमति देती है।",
        impact_en="Attackers can steal session cookies, redirect users, or perform actions on behalf of victims.",
        impact_hi="हमलावर सत्र कुकीज़ चुरा सकते हैं, उपयोगकर्ताओं को रीडायरेक्ट कर सकते हैं, या पीड़ितों की ओर से कार्य कर सकते हैं।",
        steps_en=(
            "1. Identify user input fields that reflect content back to the page",
            "2. Test input fields with basic XSS payloads like <script>alert(1)</script>",
            "3. Check if the payload is rendered in the HTML without encoding",
            "4. Verify script execution in browser developer tools",
        ),
        steps_hi=(
            "1. उपयोगकर्ता इनपुट फ़ील्ड्स की पहचान करें जो सामग्री को पेज पर वापस दर्शाती हैं",
            "2. <script>alert(1)</script> जैसे बेसिक XSS पेलोड के साथ इनपुट फ़ील्ड्स का परीक्षण करें",
            "3. जांचें कि पेलोड बिना एन्कोडिंग के HTML में रेंडर हो रहा है",
            "4. ब्राउज़र डेवलपर टूल्स में स्क्रिप्ट निष्पादन सत्यापित करें",
        ),
        cwe_id="CWE-79",
        source=KnowledgeSource.CWE
    ),
    BugType.SQLI: BugExplanation(
        bug_type=BugType.SQLI,
        title_en="SQL Injection (SQLi)",
        title_hi="SQL इंजेक्शन (SQLi)",
        description_en="A vulnerability that allows attackers to interfere with database queries by injecting malicious SQL code.",
        description_hi="एक कमजोरी जो हमलावरों को दुर्भावनापूर्ण SQL कोड इंजेक्ट करके डेटाबेस क्वेरीज़ में हस्तक्षेप करने की अनुमति देती है।",
        impact_en="Attackers can read, modify, or delete database data, and potentially gain server access.",
        impact_hi="हमलावर डेटाबेस डेटा पढ़ सकते हैं, संशोधित कर सकते हैं, या हटा सकते हैं, और संभावित रूप से सर्वर एक्सेस प्राप्त कर सकते हैं।",
        steps_en=(
            "1. Identify input fields that interact with databases",
            "2. Test with single quote (') to check for SQL errors",
            "3. Try basic payloads like ' OR 1=1--",
            "4. Analyze error messages for database information",
        ),
        steps_hi=(
            "1. डेटाबेस के साथ इंटरैक्ट करने वाले इनपुट फ़ील्ड्स की पहचान करें",
            "2. SQL त्रुटियों की जांच के लिए सिंगल कोट (') के साथ परीक्षण करें",
            "3. ' OR 1=1-- जैसे बेसिक पेलोड आज़माएं",
            "4. डेटाबेस जानकारी के लिए त्रुटि संदेशों का विश्लेषण करें",
        ),
        cwe_id="CWE-89",
        source=KnowledgeSource.CWE
    ),
    BugType.IDOR: BugExplanation(
        bug_type=BugType.IDOR,
        title_en="Insecure Direct Object Reference (IDOR)",
        title_hi="असुरक्षित प्रत्यक्ष वस्तु संदर्भ (IDOR)",
        description_en="A vulnerability where user-supplied input is used to access objects directly without proper authorization checks.",
        description_hi="एक कमजोरी जहां उपयोगकर्ता द्वारा प्रदत्त इनपुट का उपयोग उचित प्राधिकरण जांच के बिना सीधे वस्तुओं तक पहुंचने के लिए किया जाता है।",
        impact_en="Attackers can access other users' data by modifying object identifiers.",
        impact_hi="हमलावर ऑब्जेक्ट आइडेंटिफायर को संशोधित करके अन्य उपयोगकर्ताओं के डेटा तक पहुंच सकते हैं।",
        steps_en=(
            "1. Identify endpoints with object IDs in URLs or parameters",
            "2. Create two test accounts with different permissions",
            "3. Try accessing one account's resources using another's session",
            "4. Check if authorization is properly enforced",
        ),
        steps_hi=(
            "1. URL या पैरामीटर में ऑब्जेक्ट ID वाले एंडपॉइंट्स की पहचान करें",
            "2. विभिन्न अनुमतियों के साथ दो टेस्ट खाते बनाएं",
            "3. दूसरे के सत्र का उपयोग करके एक खाते के संसाधनों तक पहुंचने का प्रयास करें",
            "4. जांचें कि प्राधिकरण ठीक से लागू है",
        ),
        cwe_id="CWE-639",
        source=KnowledgeSource.CWE
    ),
    BugType.SSRF: BugExplanation(
        bug_type=BugType.SSRF,
        title_en="Server-Side Request Forgery (SSRF)",
        title_hi="सर्वर-साइड रिक्वेस्ट फोर्जरी (SSRF)",
        description_en="A vulnerability that allows attackers to make the server send requests to unintended locations.",
        description_hi="एक कमजोरी जो हमलावरों को सर्वर से अनपेक्षित स्थानों पर अनुरोध भेजने की अनुमति देती है।",
        impact_en="Attackers can access internal services, cloud metadata, or scan internal networks.",
        impact_hi="हमलावर आंतरिक सेवाओं, क्लाउड मेटाडेटा तक पहुंच सकते हैं, या आंतरिक नेटवर्क स्कैन कर सकते हैं।",
        steps_en=(
            "1. Identify features that fetch external resources",
            "2. Test with internal IP addresses (127.0.0.1, 169.254.169.254)",
            "3. Check for access to cloud metadata endpoints",
            "4. Try different URL schemes (file://, gopher://)",
        ),
        steps_hi=(
            "1. बाहरी संसाधनों को प्राप्त करने वाली सुविधाओं की पहचान करें",
            "2. आंतरिक IP पतों (127.0.0.1, 169.254.169.254) के साथ परीक्षण करें",
            "3. क्लाउड मेटाडेटा एंडपॉइंट्स तक पहुंच की जांच करें",
            "4. विभिन्न URL स्कीम (file://, gopher://) आज़माएं",
        ),
        cwe_id="CWE-918",
        source=KnowledgeSource.CWE
    ),
    BugType.CSRF: BugExplanation(
        bug_type=BugType.CSRF,
        title_en="Cross-Site Request Forgery (CSRF)",
        title_hi="क्रॉस-साइट रिक्वेस्ट फोर्जरी (CSRF)",
        description_en="A vulnerability that tricks users into performing unintended actions on authenticated sites.",
        description_hi="एक कमजोरी जो उपयोगकर्ताओं को प्रमाणित साइटों पर अनपेक्षित कार्य करने के लिए धोखा देती है।",
        impact_en="Attackers can perform actions on behalf of authenticated users without their knowledge.",
        impact_hi="हमलावर प्रमाणित उपयोगकर्ताओं की जानकारी के बिना उनकी ओर से कार्य कर सकते हैं।",
        steps_en=(
            "1. Identify state-changing endpoints (POST, PUT, DELETE)",
            "2. Check for CSRF token validation",
            "3. Create a malicious HTML page with auto-submitting form",
            "4. Test if action is performed when victim visits the page",
        ),
        steps_hi=(
            "1. स्थिति-परिवर्तन एंडपॉइंट्स (POST, PUT, DELETE) की पहचान करें",
            "2. CSRF टोकन सत्यापन की जांच करें",
            "3. ऑटो-सबमिट फॉर्म के साथ एक दुर्भावनापूर्ण HTML पेज बनाएं",
            "4. परीक्षण करें कि जब पीड़ित पेज पर जाता है तो कार्रवाई होती है",
        ),
        cwe_id="CWE-352",
        source=KnowledgeSource.CWE
    ),
    BugType.XXE: BugExplanation(
        bug_type=BugType.XXE,
        title_en="XML External Entity (XXE) Injection",
        title_hi="XML एक्सटर्नल एंटिटी (XXE) इंजेक्शन",
        description_en="A vulnerability in XML parsers that allows attackers to include external entities.",
        description_hi="XML पार्सर्स में एक कमजोरी जो हमलावरों को बाहरी इकाइयों को शामिल करने की अनुमति देती है।",
        impact_en="Attackers can read local files, perform SSRF, or cause denial of service.",
        impact_hi="हमलावर स्थानीय फ़ाइलें पढ़ सकते हैं, SSRF कर सकते हैं, या सेवा से इनकार कर सकते हैं।",
        steps_en=(
            "1. Identify endpoints accepting XML input",
            "2. Test with basic XXE payload referencing /etc/passwd",
            "3. Check if external entity is processed and returned",
            "4. Try out-of-band techniques for blind XXE",
        ),
        steps_hi=(
            "1. XML इनपुट स्वीकार करने वाले एंडपॉइंट्स की पहचान करें",
            "2. /etc/passwd को संदर्भित करने वाले बेसिक XXE पेलोड से परीक्षण करें",
            "3. जांचें कि बाहरी इकाई प्रोसेस और रिटर्न हुई है",
            "4. ब्लाइंड XXE के लिए आउट-ऑफ-बैंड तकनीकें आज़माएं",
        ),
        cwe_id="CWE-611",
        source=KnowledgeSource.CWE
    ),
    BugType.PATH_TRAVERSAL: BugExplanation(
        bug_type=BugType.PATH_TRAVERSAL,
        title_en="Path Traversal (Directory Traversal)",
        title_hi="पाथ ट्रैवर्सल (डायरेक्टरी ट्रैवर्सल)",
        description_en="A vulnerability allowing access to files outside the intended directory.",
        description_hi="एक कमजोरी जो इच्छित निर्देशिका के बाहर फ़ाइलों तक पहुंच की अनुमति देती है।",
        impact_en="Attackers can read sensitive files like configuration or password files.",
        impact_hi="हमलावर कॉन्फ़िगरेशन या पासवर्ड फ़ाइलों जैसी संवेदनशील फ़ाइलें पढ़ सकते हैं।",
        steps_en=(
            "1. Identify file path parameters in URLs or requests",
            "2. Test with ../ sequences to traverse directories",
            "3. Try encoded variants like %2e%2e%2f",
            "4. Attempt to access known files like /etc/passwd",
        ),
        steps_hi=(
            "1. URL या अनुरोधों में फ़ाइल पथ पैरामीटर की पहचान करें",
            "2. डायरेक्टरी ट्रैवर्स करने के लिए ../ अनुक्रमों से परीक्षण करें",
            "3. %2e%2e%2f जैसे एन्कोडेड वेरिएंट आज़माएं",
            "4. /etc/passwd जैसी ज्ञात फ़ाइलों तक पहुंचने का प्रयास करें",
        ),
        cwe_id="CWE-22",
        source=KnowledgeSource.CWE
    ),
    BugType.OPEN_REDIRECT: BugExplanation(
        bug_type=BugType.OPEN_REDIRECT,
        title_en="Open Redirect",
        title_hi="ओपन रीडायरेक्ट",
        description_en="A vulnerability where user input controls redirect destinations.",
        description_hi="एक कमजोरी जहां उपयोगकर्ता इनपुट रीडायरेक्ट गंतव्यों को नियंत्रित करता है।",
        impact_en="Attackers can redirect users to phishing sites while appearing legitimate.",
        impact_hi="हमलावर उपयोगकर्ताओं को फ़िशिंग साइटों पर रीडायरेक्ट कर सकते हैं जबकि वैध दिखते हैं।",
        steps_en=(
            "1. Identify redirect parameters (url, next, redirect, etc.)",
            "2. Test with external URLs as redirect targets",
            "3. Try bypass techniques like //evil.com or \\/evil.com",
            "4. Check if validation can be bypassed",
        ),
        steps_hi=(
            "1. रीडायरेक्ट पैरामीटर (url, next, redirect, आदि) की पहचान करें",
            "2. रीडायरेक्ट लक्ष्यों के रूप में बाहरी URL से परीक्षण करें",
            "3. //evil.com या \\/evil.com जैसी बायपास तकनीकें आज़माएं",
            "4. जांचें कि सत्यापन को बायपास किया जा सकता है",
        ),
        cwe_id="CWE-601",
        source=KnowledgeSource.CWE
    ),
    BugType.RCE: BugExplanation(
        bug_type=BugType.RCE,
        title_en="Remote Code Execution (RCE)",
        title_hi="रिमोट कोड एक्ज़ीक्यूशन (RCE)",
        description_en="A critical vulnerability allowing attackers to execute arbitrary code on the server.",
        description_hi="एक गंभीर कमजोरी जो हमलावरों को सर्वर पर मनमाना कोड निष्पादित करने की अनुमति देती है।",
        impact_en="Complete system compromise - attackers gain full control of the server.",
        impact_hi="पूर्ण सिस्टम समझौता - हमलावर सर्वर का पूर्ण नियंत्रण प्राप्त करते हैं।",
        steps_en=(
            "1. Identify code execution vectors (eval, exec, system calls)",
            "2. Test with simple command like 'id' or 'whoami'",
            "3. Check for serialization vulnerabilities",
            "4. Look for file upload leading to code execution",
        ),
        steps_hi=(
            "1. कोड निष्पादन वेक्टर (eval, exec, सिस्टम कॉल) की पहचान करें",
            "2. 'id' या 'whoami' जैसे सरल कमांड से परीक्षण करें",
            "3. सीरियलाइज़ेशन कमजोरियों की जांच करें",
            "4. कोड निष्पादन की ओर ले जाने वाले फ़ाइल अपलोड को देखें",
        ),
        cwe_id="CWE-94",
        source=KnowledgeSource.CWE
    ),
    BugType.LFI: BugExplanation(
        bug_type=BugType.LFI,
        title_en="Local File Inclusion (LFI)",
        title_hi="लोकल फ़ाइल इनक्लूज़न (LFI)",
        description_en="A vulnerability allowing inclusion of local files from the server.",
        description_hi="सर्वर से स्थानीय फ़ाइलों को शामिल करने की अनुमति देने वाली कमजोरी।",
        impact_en="Attackers can read source code, configuration files, or achieve RCE.",
        impact_hi="हमलावर स्रोत कोड, कॉन्फ़िगरेशन फ़ाइलें पढ़ सकते हैं, या RCE प्राप्त कर सकते हैं।",
        steps_en=(
            "1. Identify file inclusion parameters",
            "2. Test with path traversal to include known files",
            "3. Try PHP wrappers like php://filter for source disclosure",
            "4. Check for log poisoning opportunities for RCE",
        ),
        steps_hi=(
            "1. फ़ाइल समावेशन पैरामीटर की पहचान करें",
            "2. ज्ञात फ़ाइलों को शामिल करने के लिए पथ ट्रैवर्सल से परीक्षण करें",
            "3. स्रोत प्रकटीकरण के लिए php://filter जैसे PHP रैपर आज़माएं",
            "4. RCE के लिए लॉग पॉइज़निंग अवसरों की जांच करें",
        ),
        cwe_id="CWE-98",
        source=KnowledgeSource.CWE
    ),
    BugType.UNKNOWN: BugExplanation(
        bug_type=BugType.UNKNOWN,
        title_en="Unknown Vulnerability Type",
        title_hi="अज्ञात कमजोरी प्रकार",
        description_en="This vulnerability type is not recognized in the knowledge base.",
        description_hi="यह कमजोरी प्रकार ज्ञान आधार में मान्यता प्राप्त नहीं है।",
        impact_en="Impact cannot be determined without identifying the vulnerability type.",
        impact_hi="कमजोरी प्रकार की पहचान किए बिना प्रभाव निर्धारित नहीं किया जा सकता।",
        steps_en=(
            "1. Gather more information about the vulnerability",
            "2. Consult security references (CVE, CWE databases)",
            "3. Seek expert assistance if needed",
        ),
        steps_hi=(
            "1. कमजोरी के बारे में अधिक जानकारी एकत्र करें",
            "2. सुरक्षा संदर्भ (CVE, CWE डेटाबेस) से परामर्श करें",
            "3. यदि आवश्यक हो तो विशेषज्ञ सहायता लें",
        ),
        cwe_id=None,
        source=KnowledgeSource.UNKNOWN
    ),
}


def get_known_explanations() -> Dict[BugType, BugExplanation]:
    """
    Get the knowledge registry of bug explanations.
    
    Returns:
        Dictionary mapping BugType to BugExplanation
    """
    return _KNOWLEDGE_REGISTRY
