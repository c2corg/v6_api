# Based on https://github.com/monperrus/crawler-user-agents
# and https://stackoverflow.com/a/33941034
import re

bot_pattern = (
    r"(googlebot\/|bot|Googlebot-Mobile|Googlebot-Image|Google "
    r"favicon|Mediapartners-Google|bingbot|slurp|java|wget|curl|"
    r"Commons-HttpClient|Python-urllib|libwww|httpunit|nutch|phpcrawl|"
    r"msnbot|jyxobot|FAST-WebCrawler|FAST Enterprise Crawler|biglotron|"
    r"teoma|convera|seekbot|gigablast|exabot|ngbot|ia_archiver|"
    r"GingerCrawler|webmon |httrack|webcrawler|grub.org|"
    r"UsineNouvelleCrawler|antibot|netresearchserver|speedy|fluffy|"
    r"bibnum.bnf|findlink|msrbot|panscient|yacybot|AISearchBot|IOI|"
    r"ips-agent|tagoobot|MJ12bot|dotbot|woriobot|yanga|buzzbot|mlbot|"
    r"yandexbot|purebot|Linguee Bot|Voyager|CyberPatrol|voilabot|"
    r"baiduspider|citeseerxbot|spbot|twengabot|postrank|turnitinbot|"
    r"scribdbot|page2rss|sitebot|linkdex|Adidxbot|blekkobot|ezooms|"
    r"dotbot|Mail.RU_Bot|discobot|heritrix|findthatfile|europarchive.org|"
    r"NerdByNature.Bot|sistrix crawler|ahrefsbot|Aboundex|domaincrawler|"
    r"wbsearchbot|summify|ccbot|edisterbot|seznambot|ec2linkfinder|"
    r"gslfbot|aihitbot|intelium_bot|facebookexternalhit|yeti|"
    r"RetrevoPageAnalyzer|lb-spider|sogou|lssbot|careerbot|wotbox|wocbot|"
    r"ichiro|DuckDuckBot|lssrocketcrawler|drupact|webcompanycrawler|"
    r"acoonbot|openindexspider|gnam gnam spider|web-archive-net.com.bot|"
    r"backlinkcrawler|coccoc|integromedb|content crawler spider|"
    r"toplistbot|seokicks-robot|it2media-domain-crawler|ip-web-crawler.com|"
    r"siteexplorer.info|elisabot|proximic|changedetection|blexbot|"
    r"arabot|WeSEE:Search|niki-bot|CrystalSemanticsBot|rogerbot|360Spider|"
    r"psbot|InterfaxScanBot|Lipperhey SEO Service|CC Metadata Scaper|"
    r"g00g1e.net|GrapeshotCrawler|urlappendbot|brainobot|fr-crawler|"
    r"binlar|SimpleCrawler|Livelapbot|Twitterbot|cXensebot|smtbot|"
    r"bnf.fr_bot|A6-Indexer|ADmantX|Facebot|Twitterbot|OrangeBot|"
    r"memorybot|AdvBot|MegaIndex|SemanticScholarBot|ltx71|nerdybot|"
    r"xovibot|BUbiNG|Qwantify|archive.org_bot|Applebot|TweetmemeBot|"
    r"crawler4j|findxbot|SemrushBot|yoozBot|lipperhey|y!j-asr|"
    r"Domain Re-Animator Bot|AddThis)"
)


def is_crawler(user_agent):
    bot_regex = re.compile(bot_pattern, re.IGNORECASE)
    return bot_regex.search(user_agent)
