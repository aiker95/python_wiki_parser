# -*- coding: utf-8 -*-
# author: Ermilov Dmitry 
# python v.3.7
# Вся работа выполняется в асинхронной функции на python3.6 или старше
# requirements:
# aiohttp==3.5.4
# SQLAlchemy==1.2.17
# validators==0.12.4

import re
import uuid
import asyncio
from traceback import format_exc
from datetime import datetime
import functools
from aiohttp import ClientSession
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, ForeignKey
from sqlalchemy.orm import sessionmaker
import validators

def logger(func):

    '''Логирование ошибок в файл "log.txt" не изменяя имя исходной фукнкции'''

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        try:
            result = func (*args, **kwargs)
            return result
        except:
            with open("log.txt", "a") as f:
                for s in format_exc().splitlines():
                    t = datetime.now()
                    f.write(t.strftime("%d.%m.%Y  %H:%M:%S") + " " + s + "\n")
                f.write("---------------------------------------------------------------------------------------------")
            print('Error! Details in the file "log.txt" ')
    return wrapped
urls = [(input('Enter the Wikipedia address: '), str(uuid.uuid4()))]
max_depth = 6

# На входе у функции список кортежей длиной не менее 1;
# В кортеже: 1-й элемент - ссылка на страницу википедии, 2-й - идентификатор

@logger
def get_links_to_wiki_asynchronously(urls: list, max_depth: int):  

    '''Сам ррекурсивный парсер с журналированием на заданную глубину (6)'''

    metadata = MetaData()
    pages_table = Table('pages', metadata,
                        Column('id', String(36), primary_key=True),
                        Column('url', String),
               		Column('request_depth', Integer)
                       )
    relationships_table = Table('relationships', metadata,
                                 Column('from_page_id', String(36), ForeignKey("pages.id")),
                                 Column('link_id', String(36), ForeignKey("pages.id"))
                               )
    engine = create_engine("sqlite:///wiki_link.db")
    metadata.create_all(engine)

    def start_getting(urls, request_depth):
        async def fetch(url, session):
            async with session.get(url[0]) as response:
                match = re.search(r'.wikipedia.org', url[0])  # Для работы с различными языками
                article_pattern = r'<a href="/wiki/(.+?)"'  # Поиск ссылок только на статьи википедии
                from_page_id = url[1]
                return [(from_page_id, str(uuid.uuid4()), url[0][:match.start()] + '.wikipedia.org/wiki/' + i)
                        for i in re.findall(article_pattern, await response.text())]

        async def run(urls, request_depth):
            if len(urls) == 1:
                with engine.connect() as conn:
                    conn.execute(pages_table.insert().values({'id': urls[0][1], 'url': urls[0][0], 'request_depth': 0}))
            tasks = []

            # Извлечь все ответы в рамках одного сеанса клиента
            # и поддерживать соединение в активном состоянии для всех запросов.

            async with ClientSession() as session:
                for url in urls:
                    task = asyncio.ensure_future(fetch(url, session))
                    tasks.append(task)

                # Теперь в этой переменной есть все тела ответа

                responses = await asyncio.gather(*tasks)
                lst_pages_table = []
                lst_relationships_table = []
                for item in responses:
                    for inner_item in item:
                        if len(lst_pages_table) < 300 and len(lst_relationships_table) < 300:
                            lst_pages_table.append({'id': inner_item[1], 'url': inner_item[2],
                                                    'request_depth': str(request_depth)})
                            lst_relationships_table.append({'from_page_id': inner_item[0], 'link_id': inner_item[1]})
                        else:
                            with engine.connect() as conn:
                                conn.execute(pages_table.insert().values(lst_pages_table))
                                conn.execute(relationships_table.insert().values(lst_relationships_table))
                            lst_pages_table.clear()
                            lst_relationships_table.clear()
                            lst_pages_table.append({'id': inner_item[1], 'url': inner_item[2],
                                                    'request_depth': str(request_depth)})
                            lst_relationships_table.append({'from_page_id': inner_item[0], 'link_id': inner_item[1]})
                with engine.connect() as conn:
                    conn.execute(pages_table.insert().values(lst_pages_table))
                    conn.execute(relationships_table.insert().values(lst_relationships_table))

        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(run(urls, request_depth))
        loop.run_until_complete(future)

    request_depth = 1
    if validators.url(urls[0][0]):
        if re.search('wikipedia', urls[0][0]):
            while request_depth <= max_depth:
                if request_depth == 1:
                    start_getting(urls, request_depth)
                    request_depth += 1
                else:
                    # Создать настроенный класс "Session"

                    Session = sessionmaker(bind=engine)

                    # Создать сессию

                    session = Session()
                    count = session.query(pages_table).count()
                    num = 1
                    while num <= count:
                        urls.clear()
                        query = list(engine.execute('SELECT rowid,* ' +
                                                    'FROM pages ' +
                                                    'WHERE rowid >= ' + str(num) +
                                                    ' LIMIT 100'))
                        urls = [(i[2], i[1]) for i in query]
                        start_getting(urls, request_depth)
                        num += 100
                    request_depth += 1
        else:
            print("Error! The URL you entered does not point to Wikipedia.")
    else:
        print("Error! Invalid URL specified.")

get_links_to_wiki_asynchronously(urls, max_depth)