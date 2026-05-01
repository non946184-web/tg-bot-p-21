import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import List, Dict, Optional
import logging
from config import TIMETABLE_URL, CACHE_TTL
from database import Database

logger = logging.getLogger(__name__)

class TimetableParser:
    def __init__(self):
        self.db = Database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_timetable(self, target_date: date = None) -> Optional[List[Dict]]:
        """Получение расписания на дату"""
        if target_date is None:
            target_date = date.today()
        
        date_str = target_date.strftime('%Y-%m-%d')
        cache_key = target_date.strftime('%Y-%m-%d')
        
        # Проверка кэша
        cached = self.db.get_cached_timetable(cache_key, CACHE_TTL)
        if cached:
            logger.info(f"Расписание на {date_str} взято из кэша")
            return eval(cached)
        
        try:
            # Формирование запроса
            params = {
                'year': target_date.year,
                'month': target_date.month
            }
            
            response = self.session.get(TIMETABLE_URL, params=params, timeout=10)
            response.raise_for_status()
            
            # Парсинг HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            lessons = self._parse_lessons(soup, target_date)
            
            # Кэширование
            self.db.cache_timetable(cache_key, str(lessons))
            
            logger.info(f"Расписание на {date_str} спарсено: {len(lessons)} пар")
            return lessons
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к сайту: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return None
    
    def _parse_lessons(self, soup: BeautifulSoup, target_date: date) -> List[Dict]:
        """Парсинг уроков из HTML"""
        lessons = []
        
        # Ищем таблицу с расписанием
        table = soup.find('table', {'class': 'timetable'})
        if not table:
            table = soup.find('table')
        
        if not table:
            logger.warning("Таблица расписания не найдена")
            return lessons
        
        # Парсинг строк таблицы
        rows = table.find_all('tr')[1:]  # Пропускаем заголовок
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                try:
                    lesson = {
                        'time': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                        'subject': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                        'room': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                        'date': target_date.strftime('%Y-%m-%d')
                    }
                    
                    # Фильтруем пустые строки
                    if lesson['subject'] and lesson['subject'] != '-':
                        lessons.append(lesson)
                        
                except Exception as e:
                    logger.warning(f"Ошибка парсинга строки: {e}")
                    continue
        
        return lessons
    
    def get_passed_lessons(self, subject_code: str = None) -> Dict[str, int]:
        """Подсчёт прошедших пар по предметам"""
        today = date.today()
        passed = {}
        
        # Получаем расписание с начала семестра до сегодня
        # Для простоты берём текущий месяц
        for day in range(1, today.day + 1):
            try:
                check_date = date(today.year, today.month, day)
                if check_date.weekday() < 5:  # Только будни
                    lessons = self.get_timetable(check_date)
                    if lessons:
                        for lesson in lessons:
                            subject = lesson['subject']
                            # Ищем соответствие коду предмета
                            if subject_code:
                                if subject_code in subject:
                                    passed[subject_code] = passed.get(subject_code, 0) + 1
                            else:
                                # Считаем все предметы
                                for code in self._get_subject_codes():
                                    if code in subject:
                                        passed[code] = passed.get(code, 0) + 1
            except Exception as e:
                logger.warning(f"Ошибка обработки даты {check_date}: {e}")
                continue
        
        return passed
    
    def _get_subject_codes(self) -> List[str]:
        """Получение списка кодов предметов"""
        from config import DEFAULT_SUBJECTS
        return list(DEFAULT_SUBJECTS.keys())
    
    def format_timetable(self, lessons: List[Dict]) -> str:
        """Форматирование расписания в текст"""
        if not lessons:
            return "📭 На этот день пар нет"
        
        text = "📅 **Расписание**\n\n"
        
        for i, lesson in enumerate(lessons, 1):
            text += f"{i}. ⏰ {lesson['time']}\n"
            text += f"   📚 {lesson['subject']}\n"
            if lesson['room']:
                text += f"   🚪 Ауд. {lesson['room']}\n"
            text += "\n"
        
        return text
