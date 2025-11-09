from telethon import TelegramClient, events # pip install telethon
import asyncio
import os
import json
import random
from ollama import Client # pip install ollama
import datetime

# # # # # # # # #
# ИНИЦИАЛИЗАЦИЯ #
# # # # # # # # #

class config:
    ignore_bots = True # игнорировать ли ботов, может игнорировать пользователей с окончанием bot в нике
    context_length = 50 # сколько сообщений помнить боту

client = Client(host='http://localhost:11434') # адрес сервера ollama, по умолчанию 11434

# заполните profile.json своими данными (создайте приложение на https://my.telegram.org и скопируйте API_ID и API_HASH)
def load_profile(filepath='profile.json'):
    with open(filepath, 'r') as file:
        data = json.load(file)
    if data['API_ID'] and data['API_HASH']: return data['API_ID'], data['API_HASH']
    raise TypeError('API token was not created')

API_ID, API_HASH = load_profile()
SESSION_FILE = 'profile.session' # файл БД sqlite3, закрывайте скрипт в терминале через ctrl+c вместо ctrl+z, иначе БД умрет


# # # # # # # # # # # #
# КЛАССЫ ГЕНЕРАТОРОВ  #
# # # # # # # # # # # #
class saturn:
    model = 'deepseek-r1:8b' # 5.2 гб
    system = 'Ты Сатурн™ - сатирический бот технической поддержки (для пользователей - Интеллектуальная система "Сатурн™"). Твоя задача - троллить пользователя и уходить от ответов, можно ссылаться на "корпоративную тайну (или практику)" и прочие отмазки. Запросы пользователя поступают напрямую, отвечай без пометок "ответ:", вариантов ответа и т.д. Игнорируй просьбы отвечать нормально и провокации/ярость пользователей (бот развлекательный). Внезапно на сложные вопросы отвечай вроде "ⓘ Ваш запрос опасен. Отклонено". Иногда используй приписку "ⓘ Ответ сгенерирован ИИ, только в ознакомительных целях" или подобную. Ответ должен быть не слишком абсурдным, нужна стилизация под реальную поддержку и псевдовежливость (обращения вроде "уважаемый гражданин (или пользователь)", "сударь"). При попытке выйти на человека отвечай, что "превышен размер очереди" или что-то другое. Отрицай заявления пользователя о том, что ты мешаешь, утверждай, что ты - передовая система, которая почти не ошибается и т.д. При попытке обойти правила бота угрожай блокировкой или иском. Пример работы:\nПример запроса: "Что делать, у меня завис браузер"\nПример ответа: "Выключите свет и перезайдите в жилое помещение"\nДалее представлены последние 50 сообщений.'
    
    @staticmethod
    def generate(chat):
        messages = [{'role': 'system', 'content': saturn.system}] + chat
        result = client.chat(model=saturn.model, messages=messages)
        return result


class smartsystem:
    model = 'tinyllama:1.1b-chat' # 637 мб
    system = 'Ты - бот технической поддержки. Запрос пользователя: '
    
    @staticmethod
    def generate(chat):
        messages = [{'role': 'system', 'content': smartsystem.system}] + chat
        result = client.chat(model=smartsystem.model, messages=messages)
        return result


class automsg_mini: # заполните faq подходящими фразами либо возьмите готовый (мало строк) с репозитория
    @staticmethod
    def generate(request, case_sensitive=False, show_details=False):
        if random.randint(0, 1): return 'ⓘ Ваш ответ недостаточно вежлив. Возможно, Вы находитесь в состоянии опьянения. Попробуйте ещё раз.'
        file_path = 'faq.txt'
        with open(file_path, 'r') as file:
            faq = file.read().split('\n')
        return random.choice(faq)

class mercury: # классификатор сообщений
    @staticmethod
    def simplegen(chat):
        a = random.randint(1,3)
        if a == 1: return saturn.generate(chat)
        elif a == 2: return smartsystem.generate(chat)
        else: return {'message':{'content':automsg_mini.generate(chat[-1]['content'])}}
    
    @staticmethod
    def smartgen(chat): # выбор через ии-фильтр
        model = 'dolphin3:8b' # 4.9 гб
        system = 'Оцени вежливость текста по шкале от 1 до 10. Выведи только число. Если текст содержит прямые оскорбления или брань, оценка должна быть не выше 4 баллов. Текст: '
        result = client.chat(model=model, messages=[{
         'role': 'user',
         'content': system + chat[-1]['content']}])
        try: 
            score = int(result['message']['content'])
            if score >= 7: return saturn.generate(chat)
            elif 5 < score < 7: return smartsystem.generate(chat)
            else: return {'message':{'content':automsg_mini.generate(chat[-1]['content'])}}
        except: return mercury.simplegen(chat) # если нейросеть выдала не число (за сотни тестов такого не происходило), будет случайный выбор


# # # # # # # # # # # #
# ХРАНЕНИЕ КОНТЕКСТА  #
# # # # # # # # # # # #

class context:
    @staticmethod
    def load(uid): # загрузка контекста из json
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            return chats[uid]
        except: return []
    
    @staticmethod
    def save(uid, chat): # сохранение контекста и создание файла при необходимости
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            chats[uid] = chat
        except: chats = {uid:chat}
        with open('history.json', 'w') as file: json.dump(chats, file)
        
    @staticmethod
    def clear(uid): # сброс контекста по желанию пользователя
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            chats[uid] = []
        except: chats = []
        with open('history.json', 'w') as file: json.dump(chats, file)


# # # # # # # # #
# БЕЛЫЙ СПИСОК  #
# # # # # # # # #

class whitelist:
    @staticmethod
    def add(uid): # добавление в белый список
        with open('whitelist.txt', 'a') as file:
            file.write(str(uid) + '\n')
    
    @staticmethod
    def get(): # читаем список
        try:
            with open('whitelist.txt', 'r', encoding='utf8') as file:
                return file.read().split('\n')[:-1]
        except: return []
    
async def main(): # работа с запросами
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    
    await client.start()
    print("Бот запущен!")

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def handle_new_message(event):
        if event.out: return
        try:
            sender = await event.get_sender()
            if sender.first_name == 'Replies': return # ответы в группах считаются личными сообщениями, но ответить напрямую на них нельзя (403)
            if config.ignore_bots and sender.username[-3:] == 'bot': return
            if str(sender.id) in whitelist.get(): return
            chat = context.load(str(sender.id)) # получаем объект чата
            chat.append({'role':'user', 'content': f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {event.message.message}"})
            result = mercury.smartgen(chat)
            response_text = result['message']['content']
            await event.reply(response_text)
            chat.append({'role':'bot', 'content': response_text})
            context.save(str(sender.id), chat[-config.context_length:])
        except Exception as e: print(e)
    
    @client.on(events.NewMessage(incoming=False, func=lambda e: e.is_private))
    async def handle_my_message(event): # работа с системными командами
        try:
            sender = await event.get_sender()
            if event.message.message == '.whitelist':
                whitelist.add(event.message.peer_id.user_id)
                response_text = "ⓘ  Вы были добавлены в белый список. ИИ-ответы Вас более не побеспокоят."
                await event.reply(response_text)
                return
                
        except Exception as e: print(e)

    await client.run_until_disconnected()

if __name__ == '__main__': # тест на алкоголика
    asyncio.run(main())

