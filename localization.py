"""Locale metadata for the two static editions. Source IDs and page routes are shared."""
from html import escape
from datetime import date
# Reserve this set for any future article without a reviewed Bengali edition.
STANDALONE_PROFILE_KEYS=frozenset({'person-k-d-paul'})
ENGLISH_ONLY_KEYS=frozenset()
NO_SOCIAL_IMAGE_PROFILE_KEYS=frozenset({'person-k-d-paul'})
PAGES_BN={
'faq':('সাধারণ প্রশ্ন','আগুরী ও উগ্রক্ষত্রিয়: সাধারণ প্রশ্ন','আগুরী পরিচয়, ইতিহাস, সামাজিক অবস্থান, বসতি, পদবি ও গবেষণা সম্পর্কে সংক্ষিপ্ত উত্তর এবং আরও পড়ার পথ।'),
'bangsha-parichay-aguri-origins':('পারিবারিক ইতিহাস','বংশ-পরিচয় পাঠ','বাংলার বংশবৃত্তান্তের গ্রন্থগুলি আগুরীদের উৎপত্তি, পারিবারিক স্মৃতি ও রাঢ়ে তাঁদের স্থান সম্পর্কে কী জানায়।'),
'aguris-recognition':('স্বীকৃতির সন্ধান','আগুরীদের স্বীকৃতির সন্ধান','বাংলায় সামাজিক মর্যাদা, বিবাহ ও সমাজে স্থান'),
'rights':('স্বত্ব ও পুনর্ব্যবহার','স্বত্ব ও পুনর্ব্যবহার','সমাজের সহযোগিতায় গড়া, স্বত্ব সংরক্ষিত একটি প্রকল্প: পড়া, লিঙ্ক ভাগ করা, উদ্ধৃতি ও পুনর্ব্যবহারের অনুমতির নিয়ম।'),
'contributor-terms':('অবদান দেওয়ার শর্ত','আপনার অবদান, আপনার অধিকার','আগুরী ঐতিহ্যকে আপনি যে অনুমতি দেন, যে অধিকার আপনার থাকে এবং আপনার অবদান পর্যালোচনা ও সংরক্ষণের নিয়ম।'),
'research':('গবেষণার বিষয়','গবেষণার বিষয়','নথি, মৌখিক ইতিহাস ও ক্ষেত্রসমীক্ষার মাধ্যমে আগুরী ঐতিহ্য, অভিবাসন, ভূমি, বিবাহ ও বৈষম্য অনুসন্ধানের সম্ভাব্য প্রশ্ন।'),
'contact':('যোগাযোগ','আমাদের সঙ্গে যোগাযোগ করুন','ওয়েবসাইট বা প্রকল্প সম্পর্কে আগুরী ঐতিহ্যকে ব্যক্তিগতভাবে বার্তা পাঠান।'),
'contribute':('সহযোগিতা','ইতিহাসে আপনার সংযোজন','স্মৃতি, ছবি বা নথি ভাগ করে নিন, অথবা তথ্য সংশোধনে সাহায্য করুন। বাংলা ও ইংরেজি দুই ভাষাতেই লিখতে পারেন।'),
'review':('সম্পাদকীয় পর্যালোচনা','সহযোগিতার সম্পাদকীয় ডেস্ক','পাঠকদের জমা দেওয়া তথ্য পর্যালোচনা করুন, আরও বিবরণ চান এবং সম্পাদনার সিদ্ধান্ত নথিভুক্ত করুন।'),
'index':('প্রচ্ছদ','আগুরী ঐতিহ্য','পশ্চিমবঙ্গের আগুরী / উগ্রক্ষত্রিয় সমাজের ইতিহাস, সংস্কৃতি, অঞ্চল ও ব্যক্তিত্বের পরিচয়।'),
'history':('ইতিহাস','ইতিহাসের পথে আগুরীরা','উৎপত্তি, ভূমি, সামাজিক পরিবর্তন ও বাংলার ইতিহাসে সমাজের স্থান।'),
'origins':('উৎপত্তি','নগদী থেকে জোতদার: বর্ধমান রাজ ও আগুরীদের উৎপত্তি','আগুরী সমাজ ও বর্ধমান রাজের ইতিহাসে সৈনিকবৃত্তি, ভূমিস্বত্ব ও আত্মপরিচয় নিয়ে একটি ঐতিহাসিক ব্যাখ্যা।'),
'aguri-jotedars-dar-patnidars':('অদৃশ্য মধ্যস্তর','অদৃশ্য মধ্যস্তর','বর্ধমান রাজে আগুরি জোতদার, দর-পাটনিদার ও গ্রামীণ ক্ষমতার উত্থান'),
'culture':('সংস্কৃতি','সংস্কৃতি, রীতিনীতি ও সমাজজীবন','আগুরী সমাজের নথিতে গ্রামজীবন, পূজা, রীতি ও সংস্কার, মুদ্রণ এবং পারিবারিক স্মৃতি।'),
'aguris-today':('আজকের আগুরীরা','আজকের আগুরীরা','জমি, অভিবাসন, রাজনৈতিক অংশগ্রহণ ও সম্প্রদায়ের পরিবর্তিত জীবন।'),
'food-and-village-life':('খাদ্য ও গ্রামজীবন','আগুরীদের খাদ্যসংস্কৃতি ও গ্রামজীবন','মাছের টক, নবান্নের ভোজ, উৎসব ও বর্ধমানের গ্রামগুলির দৈনন্দিন ইতিহাস।'),
'geography':('অঞ্চল','রাঢ়বঙ্গের মাটিতে শিকড়','আগুরী ইতিহাস ও সমাজজীবনের সঙ্গে যুক্ত বর্ধমান ও পার্শ্ববর্তী জেলাগুলি।'),
'water-landscape':('নদী ও সেচভূমি','আগুরীরা ও রাঢ়বঙ্গের নদী ও সেচভূমি','রাঢ়বঙ্গের নদী, খাল ও আগুরী বসতি, চাষাবাদ এবং গ্রামীণ ক্ষমতার ইতিহাস।'),
'people':('ব্যক্তিত্ব','ইতিহাসের মানুষ','জনসেবা, চিকিৎসা, সাহিত্য, চলচ্চিত্র, শিক্ষা ও সাংবাদিকতায় বিশিষ্ট ব্যক্তিদের জীবনচরিত।'),
'surnames':('পদবী','আগুরী পদবী কোথা থেকে এল','আগুরী পদবীর অর্থ ও উৎস এবং উপাধি বদলের পিছনের পারিবারিক ইতিহাস।'),
'archives':('সাময়িকপত্র','উগ্রক্ষত্রিয়-প্রতিনিধি','আগুরী সমাজের ইতিহাসচর্চার উপকরণ হিসেবে সংরক্ষিত দুটি সাময়িকপত্রের খণ্ড।'),
 'translations':('পাঠ ও অনুবাদ','বাংলা মূল, সঙ্গে ইংরেজি অনুবাদ','ঐতিহাসিক বই, নির্বাচিত প্রবন্ধ, ভূমিকা ও সমালোচনার বাংলা উৎস এবং ইংরেজি অনুবাদ।'),
'bibliography':('উৎসসমূহ','আগুরী ঐতিহ্যের সহায়ক উপকরণ','সমাজের ইতিহাসের ভিত্তি: বই, গবেষণা, জীবনচরিত, সাময়িকপত্র ও অনূদিত রচনা।'),
'about':('প্রকল্প সম্পর্কে','সংরক্ষণের মতো এক ঐতিহ্য','আগুরী / উগ্রক্ষত্রিয় সমাজের ইতিহাস, সংস্কৃতি ও মানুষকে নিয়ে একটি স্বতন্ত্র প্রকল্প।'),
'book-rajput-o-ugrakshatriya':('ঐতিহাসিক বই','রাজপুত ও উগ্রক্ষত্রিয়','হরিচরণ বন্ধুর ইতিহাসগ্রন্থ, দ্বিতীয় সংস্করণ, ১৯৪০: বাংলা মূল ও ইংরেজি অনুবাদ পড়ুন।')}
# English strings are keys so missing translations fail the build rather than falling back silently.
UI_BN={
'Contact Us':'যোগাযোগ করুন',
'Last updated':'সর্বশেষ হালনাগাদ',
'Cite this page':'এই পাতার সূত্র উল্লেখ করুন',
'Copy citation':'সূত্রের বিবরণ কপি করুন',
'Page views':'পাতা দেখা হয়েছে',
'Citing this page does not grant permission to republish it.':'এই পাতার সূত্র উল্লেখ করলেই তা পুনঃপ্রকাশের অনুমতি পাওয়া যায় না।',
'Copyright & reuse':'স্বত্ব ও পুনর্ব্যবহার',
'Contributor terms':'অবদান দেওয়ার শর্ত',
'Rights and participation':'স্বত্ব ও সহযোগিতা',
'© 2026 Aguri Heritage. Original project material: all rights reserved.':'© ২০২৬ আগুরী ঐতিহ্য। প্রকল্পের নিজস্ব মৌলিক উপকরণের সর্বস্বত্ব সংরক্ষিত।',
'Contributors and other rights holders retain their rights. See our reuse policy.':'অবদানকারী ও অন্যান্য স্বত্বাধিকারীর অধিকার অক্ষুণ্ণ থাকে। পুনর্ব্যবহারের নীতি দেখুন।',
'Original project material: all rights reserved. Other material retains its own rights.':'প্রকল্পের নিজস্ব মৌলিক উপকরণের সর্বস্বত্ব সংরক্ষিত। অন্যান্য উপকরণের নিজস্ব স্বত্ব অক্ষুণ্ণ থাকে।',
'Research topics':'গবেষণার বিষয়',
'Sourced from the Aguri Heritage project.':'এই পাতার উৎস: Aguri Heritage (আগুরী ঐতিহ্য) প্রকল্প।',
'Aguri Heritage':'আগুরী ঐতিহ্য','Source':'উৎস','Read further':'আরও পড়ুন','Notes & sources':'টীকা ও উৎস','Source details':'উৎসের বিবরণ','Translations':'পাঠ ও অনুবাদ','Resources':'উৎসসমূহ','The heritage project':'ঐতিহ্য প্রকল্প','Resource sections':'উৎসের বিভাগ','Books & references':'বই ও তথ্যসূত্র','English translations':'মূল পাঠ ও অনুবাদ','Periodical archive':'সাময়িকপত্রের সংগ্রহ','On this page':'এই পাতায়','In this translation':'এই পাঠে','sections':'অংশ','Skip to content':'মূল লেখায় যান','An independent community heritage project':'সামাজিক ঐতিহ্যের একটি স্বতন্ত্র প্রকল্প','UGRA KSHATRIYA · WEST BENGAL':'উগ্রক্ষত্রিয় · পশ্চিমবঙ্গ','Search':'খুঁজুন','Menu':'মেনু','Main navigation':'প্রধান বিভাগ','History, culture and people.':'ইতিহাস, সংস্কৃতি ও মানুষ।','Connecting generations.':'প্রজন্মের সঙ্গে প্রজন্মের যোগসূত্র।','Explore the resources':'উপকরণগুলি দেখুন','Independent heritage project · English edition · 2026':'স্বতন্ত্র ঐতিহ্য প্রকল্প · বাংলা সংস্করণ · ২০২৬','Editorial approach':'সম্পাদনার দৃষ্টিভঙ্গি','Contribute to the collection':'সংগ্রহে সহযোগিতা করুন','Search the heritage project':'ঐতিহ্য প্রকল্পে খুঁজুন','Close search':'অনুসন্ধান বন্ধ করুন','Search English articles and source descriptions':'বাংলা নিবন্ধ ও উৎসের বিবরণে খুঁজুন','Try Bardhaman, origins, culture, Panja…':'যেমন: বর্ধমান, উৎপত্তি, সংস্কৃতি, পাঁজা…','Enter a word or phrase to begin.':'শুরু করতে একটি শব্দ বা বাক্যাংশ লিখুন।','For Bengali text inside the journals, use the':'সাময়িকপত্রের ভিতরের বাংলা লেখার জন্য ব্যবহার করুন','journal reader':'সাময়িকপত্রের পাঠাগার','Language':'ভাষা'}
UI_BN.update({
 'Contribute':'সহযোগিতা করুন',
 'Help improve this page':'এই পাতার উন্নতিতে সাহায্য করুন',
 'Have a correction or a source to add? Share it with the editors.':'কোনও সংশোধন বা নতুন তথ্যসূত্র আছে? সম্পাদকদের জানান।',
 'Suggest a correction':'সংশোধন প্রস্তাব করুন',
})
UI_BN.update({
'Share':'শেয়ার করুন',
'Share this page':'এই পাতা শেয়ার করুন',
'WhatsApp':'হোয়াটসঅ্যাপ',
'Facebook':'ফেসবুক',
'Email':'ইমেল',
'Copy link':'লিঙ্ক কপি করুন',
'Link copied.':'লিঙ্ক কপি হয়েছে।',
'Copy this link:':'এই লিঙ্কটি কপি করুন:',
'Close':'বন্ধ করুন',
'Get notified of new articles':'নতুন লেখার খবর পান',
'Notifications':'বিজ্ঞপ্তি',
'New articles, major research updates and new family profiles. At most a few a month. No tracking.':'নতুন লেখা, বড় গবেষণা-হালনাগাদ ও নতুন পারিবারিক পরিচিতি। মাসে বড়জোর কয়েকটি। কোনও ট্র্যাকিং নেই।',
'Turn on notifications':'বিজ্ঞপ্তি চালু করুন',
'Turn off notifications':'বিজ্ঞপ্তি বন্ধ করুন',
'About notifications':'বিজ্ঞপ্তি সম্পর্কে',
})
def num(n,lang):
 return str(n).translate(str.maketrans('0123456789','০১২৩৪৫৬৭৮৯')) if lang=='bn' else str(n)
def display_date(value,lang):
 day=date.fromisoformat(value)
 months=('January','February','March','April','May','June','July','August','September','October','November','December') if lang=='en' else ('জানুয়ারি','ফেব্রুয়ারি','মার্চ','এপ্রিল','মে','জুন','জুলাই','আগস্ট','সেপ্টেম্বর','অক্টোবর','নভেম্বর','ডিসেম্বর')
 return f'{num(day.day,lang)} {months[day.month-1]} {num(day.year,lang)}'
def ui(key,lang):
 return escape(UI_BN[key] if lang=='bn' else key)
