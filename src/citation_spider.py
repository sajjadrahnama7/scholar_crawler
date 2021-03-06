import scrapy
import re
import logging
import time
from src.conf import db_client, maxCArtcile, productionMode
from src.article_model import ArticleModel
from src.tor import change_ip
from src.user_agent import RandomUserAgent


class CitationSpider(scrapy.Spider):
    handle_httpstatus_list = [403, 503, 302, 31]
    dont_redirect = True
    name = "citation"

    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'COOKIES_ENABLED': False
    }

    def __init__(self):
        logging.getLogger('scrapy').setLevel(logging.ERROR)
        self.collection = db_client().scholar.citaions
        self.user_agents = RandomUserAgent()
        super().__init__()

    def start_requests(self):
        collection = db_client().scholar.articles
        cursor = collection.find({'citations_index': {"$lt": maxCArtcile}})
        for article in cursor:
            req = scrapy.Request(url=article['citations_link'] + 'start=0', callback=self.parse,
                                 meta={'article': article})
            req = self.user_agents.set_header(req)
            yield req

    def parse(self, response):
        log(response)
        scholar_url = 'https://scholar.google.com'
        for obj in response.css('.gs_r.gs_or.gs_scl .gs_ri'):
            try:
                authors, year = extract_authors(obj.css('.gs_a').xpath('string(.)').extract_first())
                data = {
                    'title': obj.css('.gs_rt a').xpath('string(.)').extract_first(),
                    'link': obj.css('.gs_rt a::attr(href)').extract_first(),
                    'authors': authors,
                    'year': year,
                    'abstract': obj.css('.gs_rs').xpath('string(.)').extract_first(),
                    'citations': int(
                        re.search('(\d+)', obj.css('.gs_fl').xpath('string(a[3])').extract_first()).group(1)),
                    'citations_link': scholar_url + obj.css('.gs_fl').xpath('a[3]/@href').extract_first() + '&as_vis=1',
                    'citations_index': -1,
                }
                model = ArticleModel(data)
                model.save()
                self.cite(model.id, response.meta['article']['_id'])
            except Exception:
                pass
        if not response.css('.gs_r.gs_or.gs_scl .gs_ri'):
            log(response, -400)
            print('400\t User Agent:  ' + str(response.request.headers['User-Agent']))
        else:
            self.collection.update_one({'_id': response.meta['article']['_id']}, {"$inc": {"citations_index": 10, }})
            print('200\t User Agent:  ' + str(response.request.headers['User-Agent']))

        start = int(re.findall('start=([\d]+)', response.url)[0]) + 10
        next_page = re.sub('start=[0-9]*$', 'start=' + str(start), response.url)

        if start < maxCArtcile:
            req = scrapy.Request(url=next_page, callback=self.parse, meta=response.meta)
            self.user_agents.set_header(req)
            yield req

    def cite(self, source, dest):
        self.collection.insert_one({
            'source': source,
            'dest': dest,
        })


def extract_authors(raw):
    year = int(re.search('-.*(\d{4})', raw).group(1))
    raw = re.sub('….*', '', raw)
    raw = re.sub('\xa0', ' ', raw)
    raw = re.sub(' - .*', '', raw)
    raw = re.split('\s*,\s*', raw)
    return raw, year


def log(response, error=-1):
    res = re.findall('start=([\d]+)', response.url)
    start = res[0]
    res = str(response.status) + '\t'
    res += time.strftime("%m-%d %H:%M:%S", time.localtime()) + '\t'
    res += start + '\t'
    res += str(response.meta['article']['_id']) + '\n'
    if error != -1:
        res = 'ERROR\t' + str(error) + '\n' + res + '\n'
    with open("logs/main.txt", "a") as file:
        file.write(res)
