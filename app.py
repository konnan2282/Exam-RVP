import os
import hashlib
import bleach
import markdown
import csv
import io
from datetime import datetime, date, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, session, make_response
from config import Config
from models import db, User, Book, Role, Genre, Cover, Review, VisitLog
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from functools import wraps
from sqlalchemy import func

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

# Убедимся, что папка для обложек существует на диске
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Для выполнения данного действия необходимо пройти процедуру аутентификации."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Кастомный фильтр Jinja2 для рендеринга Markdown
@app.template_filter('markdown')
def render_markdown(text):
    if not text:
        return ""
    return markdown.markdown(text, extensions=['fenced_code', 'tables'])

# Декоратор ролей
def role_required(*role_names):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Для выполнения данного действия необходимо пройти процедуру аутентификации.", "warning")
                return redirect(url_for('login', next=request.url))
            if current_user.role.name not in role_names:
                flash("У вас недостаточно прав для выполнения данного действия.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==================== МАРШРУТЫ ПРИЛОЖЕНИЯ ====================

# 1. Главная страница
@app.route('/')
def index():
    # Секция ПОПУЛЯРНЫЕ КНИГИ: топ-5 за последние 3 месяца
    three_months_ago = datetime.utcnow() - timedelta(days=90)
    popular_query = db.session.query(
        VisitLog.book_id,
        func.count(VisitLog.id).label('views')
    ).filter(VisitLog.created_at >= three_months_ago)\
     .group_by(VisitLog.book_id)\
     .order_by(func.count(VisitLog.id).desc())\
     .limit(5).all()

    popular_books = []
    for item in popular_query:
        book = Book.query.get(item[0])
        if book:
            book.popular_views = item[1]
            popular_books.append(book)

    # Секция НЕДАВНО ПРОСМОТРЕННЫЕ
    recent_books = []
    if current_user.is_authenticated:
        recent_logs = VisitLog.query.filter_by(user_id=current_user.id)\
                                    .order_by(VisitLog.created_at.desc()).all()
        seen = set()
        recent_book_ids = []
        for log in recent_logs:
            if log.book_id not in seen:
                seen.add(log.book_id)
                recent_book_ids.append(log.book_id)
                if len(recent_book_ids) == 5:
                    break
        recent_books = [Book.query.get(bid) for bid in recent_book_ids if Book.query.get(bid)]
    else:
        recent_book_ids = session.get('recent_views', [])
        recent_books = [Book.query.get(bid) for bid in recent_book_ids if Book.query.get(bid)]

    # Основной пагинированный список всех книг
    page = request.args.get('page', 1, type=int)
    pagination = Book.query.order_by(Book.year.desc(), Book.id.desc()).paginate(page=page, per_page=10, error_out=False)
    
    return render_template('index.html', 
                           pagination=pagination, 
                           popular_books=popular_books, 
                           recent_books=recent_books)

# 2. Вход в систему (С поддержкой запоминания и точным текстом ошибки из задания)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        login_val = request.form.get('login')
        password_val = request.form.get('password')
        remember_me = True if request.form.get('remember_me') else False
        
        user = User.query.filter_by(login=login_val).first()
        if user and check_password_hash(user.password_hash, password_val):
            login_user(user, remember=remember_me)
            flash("Вы успешно вошли в систему!", "success")
            return redirect(request.args.get('next') or url_for('index'))
        else:
            # Точный текст сообщения об ошибке из ТЗ (Задание 6)
            flash("Невозможно аутентифицироваться с указанными логином и паролем", "danger")
    return render_template('login.html')

# 3. Выход из системы
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы успешно вышли из системы.", "success")
    return redirect(request.referrer or url_for('index'))

# 4. Просмотр книги
@app.route('/books/<int:book_id>')
def view_book(book_id):
    book = Book.query.get_or_404(book_id)
    # Используем UTC дату для точной синхронизации суточных логов с СУБД
    today = datetime.utcnow().date()
    record_visit = False

    # УЧЕТ ПОСЕЩЕНИЙ
    if current_user.is_authenticated:
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        today_visits = VisitLog.query.filter(
            VisitLog.book_id == book.id,
            VisitLog.user_id == current_user.id,
            VisitLog.created_at >= start_of_day,
            VisitLog.created_at <= end_of_day
        ).count()

        if today_visits < 10:
            record_visit = True
            new_visit = VisitLog(book_id=book.id, user_id=current_user.id)
    else:
        if 'anon_visits' not in session:
            session['anon_visits'] = {}

        visits_dict = session['anon_visits']
        book_key = str(book.id)

        if book_key not in visits_dict:
            visits_dict[book_key] = []

        today_str = today.isoformat()
        today_anon_visits = [d for d in visits_dict[book_key] if d == today_str]

        if len(today_anon_visits) < 10:
            record_visit = True
            visits_dict[book_key].append(today_str)
            session['anon_visits'] = visits_dict
            session.modified = True
            new_visit = VisitLog(book_id=book.id, user_id=None)

        if 'recent_views' not in session:
            session['recent_views'] = []
        recent = session['recent_views']
        if book_id in recent:
            recent.remove(book_id)
        recent.insert(0, book_id)
        session['recent_views'] = recent[:5]
        session.modified = True

    if record_visit:
        try:
            db.session.add(new_visit)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Ошибка сохранения лога просмотра: {e}")

    has_reviewed = False
    user_review = None
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        if user_review:
            has_reviewed = True

    reviews = Review.query.filter_by(book_id=book.id).order_by(Review.created_at.desc()).all()

    return render_template('view_book.html', book=book, reviews=reviews, has_reviewed=has_reviewed, user_review=user_review)

# 5. Добавление новой книги
@app.route('/books/add', methods=['GET', 'POST'])
@role_required('Администратор')
def add_book():
    genres = Genre.query.all()
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        publisher = request.form.get('publisher')
        year = request.form.get('year')
        pages_count = request.form.get('pages_count')
        short_description_raw = request.form.get('short_description')
        selected_genre_ids = request.form.getlist('genres')
        cover_file = request.files.get('cover')

        try:
            year_int = int(year) if year else 0
            pages_int = int(pages_count) if pages_count else 0

            allowed_tags = ['p', 'b', 'i', 'u', 'strong', 'em', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'br', 'hr']
            allowed_attrs = {'a': ['href', 'title']}
            short_description = bleach.clean(short_description_raw, tags=allowed_tags, attributes=allowed_attrs)

            if not cover_file or cover_file.filename == '':
                flash("Необходимо загрузить обложку для книги.", "danger")
                raise ValueError("Отсутствует файл обложки")

            new_book = Book(
                title=title, author=author, publisher=publisher,
                year=year_int, pages_count=pages_int, short_description=short_description
            )
            for g_id in selected_genre_ids:
                genre = Genre.query.get(int(g_id))
                if genre:
                    new_book.genres.append(genre)

            db.session.add(new_book)
            db.session.flush()

            file_data = cover_file.read()
            md5_hash = hashlib.md5(file_data).hexdigest()
            cover_file.seek(0)

            existing_cover = Cover.query.filter_by(md5_hash=md5_hash).first()

            if existing_cover:
                new_cover = Cover(
                    file_name=existing_cover.file_name,
                    mime_type=cover_file.mimetype or existing_cover.mime_type,
                    md5_hash=md5_hash,
                    book_id=new_book.id
                )
                db.session.add(new_cover)
            else:
                new_cover = Cover(
                    file_name="temporary_name",
                    mime_type=cover_file.mimetype or 'image/jpeg',
                    md5_hash=md5_hash,
                    book_id=new_book.id
                )
                db.session.add(new_cover)
                db.session.flush()

                file_ext = os.path.splitext(cover_file.filename)[1] or '.jpg'
                file_name = f"{new_cover.id}{file_ext}"
                new_cover.file_name = file_name

                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
                cover_file.save(filepath)

            db.session.commit()
            flash("Книга успешно добавлена!", "success")
            return redirect(url_for('view_book', book_id=new_book.id))

        except Exception as e:
            db.session.rollback()
            print(f"Ошибка сохранения: {e}")
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            
            mock_book = {
                'title': title,
                'author': author,
                'publisher': publisher,
                'year': year,
                'pages_count': pages_count,
                'short_description': short_description_raw,
                'genres': [Genre.query.get(int(g_id)) for g_id in selected_genre_ids if Genre.query.get(int(g_id))]
            }
            return render_template('add_book.html', genres=genres, book=mock_book)

    return render_template('add_book.html', genres=genres)

# 6. Редактирование книги
@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@role_required('Администратор', 'Модератор')
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    genres = Genre.query.all()
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        publisher = request.form.get('publisher')
        year = request.form.get('year')
        pages_count = request.form.get('pages_count')
        short_description_raw = request.form.get('short_description')
        selected_genre_ids = request.form.getlist('genres')

        try:
            book.title = title
            book.author = author
            book.publisher = publisher
            book.year = int(year) if year else 0
            book.pages_count = int(pages_count) if pages_count else 0
            
            allowed_tags = ['p', 'b', 'i', 'u', 'strong', 'em', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'br', 'hr']
            allowed_attrs = {'a': ['href', 'title']}
            book.short_description = bleach.clean(short_description_raw, tags=allowed_tags, attributes=allowed_attrs)

            book.genres = []
            for g_id in selected_genre_ids:
                genre = Genre.query.get(int(g_id))
                if genre:
                    book.genres.append(genre)

            db.session.commit()
            flash("Данные книги успешно обновлены!", "success")
            return redirect(url_for('view_book', book_id=book.id))

        except Exception as e:
            db.session.rollback()
            print(f"Ошибка редактирования: {e}")
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            
            book.title = title
            book.author = author
            book.publisher = publisher
            book.year = year
            book.pages_count = pages_count
            book.short_description = short_description_raw
            book.genres = [Genre.query.get(int(g_id)) for g_id in selected_genre_ids if Genre.query.get(int(g_id))]
            
            return render_template('edit_book.html', book=book, genres=genres)

    return render_template('edit_book.html', book=book, genres=genres)

# 7. Удаление книги
@app.route('/books/<int:book_id>/delete', methods=['POST'])
@role_required('Администратор')
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    cover_filename = book.cover.file_name if book.cover else None
    try:
        db.session.delete(book)
        db.session.commit()

        if cover_filename:
            other_uses = Cover.query.filter_by(file_name=cover_filename).count()
            if other_uses == 0:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], cover_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)

        flash("Книга успешно удалена!", "success")
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка удаления: {e}")
        flash("Произошла ошибка при удалении книги.", "danger")

    return redirect(url_for('index'))

# 8. Создание рецензии к книге
@app.route('/books/<int:book_id>/review', methods=['GET', 'POST'])
@role_required('Пользователь', 'Модератор', 'Администратор')
def add_review(book_id):
    book = Book.query.get_or_404(book_id)
    
    existing_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
    if existing_review:
        flash("Вы уже оставили рецензию на эту книгу.", "warning")
        return redirect(url_for('view_book', book_id=book.id))

    if request.method == 'POST':
        rating = request.form.get('rating')
        review_text_raw = request.form.get('text')

        try:
            if not review_text_raw or not review_text_raw.strip():
                raise ValueError("Текст рецензии не может быть пустым.")

            rating_int = int(rating) if rating is not None else 5
            if rating_int < 0 or rating_int > 5:
                raise ValueError("Некорректная оценка.")

            # Санация текста рецензии с помощью bleach перед сохранением
            allowed_tags = [
                'p', 'b', 'i', 'u', 'strong', 'em', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                'ul', 'ol', 'li', 'br', 'hr', 'blockquote', 'code', 'pre'
            ]
            allowed_attrs = {'a': ['href', 'title']}
            text = bleach.clean(review_text_raw, tags=allowed_tags, attributes=allowed_attrs)

            new_review = Review(
                book_id=book.id,
                user_id=current_user.id,
                rating=rating_int,
                text=text
            )
            db.session.add(new_review)
            db.session.commit()

            flash("Рецензия успешно добавлена!", "success")
            return redirect(url_for('view_book', book_id=book.id))

        except Exception as e:
            db.session.rollback()
            print(f"Ошибка добавления рецензии: {e}")
            flash("При сохранении рецензии возникла ошибка. Проверьте корректность введённых данных.", "danger")
            
            return render_template('add_review.html', book=book, review_text=review_text_raw, rating=rating)

    return render_template('add_review.html', book=book)

# 9. Панель статистики Администратора
@app.route('/admin/stats')
@role_required('Администратор')
def admin_stats():
    active_tab = request.args.get('tab', 'journal')
    page_j = request.args.get('page_j', 1, type=int)
    page_s = request.args.get('page_s', 1, type=int)
    
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')

    journal_pagination = VisitLog.query.order_by(VisitLog.created_at.desc()).paginate(page=page_j, per_page=10, error_out=False)

    stats_query = db.session.query(
        Book.title,
        func.count(VisitLog.id).label('view_count')
    ).join(VisitLog, Book.id == VisitLog.book_id)\
     .filter(VisitLog.user_id.isnot(None))

    if date_from_str:
        try:
            df = datetime.strptime(date_from_str, '%Y-%m-%d')
            stats_query = stats_query.filter(VisitLog.created_at >= df)
        except ValueError:
            pass
    if date_to_str:
        try:
            dt = datetime.strptime(date_to_str, '%Y-%m-%d')
            dt = datetime.combine(dt, datetime.max.time())
            stats_query = stats_query.filter(VisitLog.created_at <= dt)
        except ValueError:
            pass

    stats_query = stats_query.group_by(Book.id).order_by(func.count(VisitLog.id).desc())
    stats_pagination = stats_query.paginate(page=page_s, per_page=10, error_out=False)

    return render_template('admin_stats.html',
                           active_tab=active_tab,
                           page_j=page_j,
                           page_s=page_s,
                           date_from=date_from_str,
                           date_to=date_to_str,
                           journal_pagination=journal_pagination,
                           stats_pagination=stats_pagination)

# 10. Генерация CSV-файлов
@app.route('/admin/stats/export/<string:export_type>')
@role_required('Администратор')
def export_csv(export_type):
    today_str = date.today().strftime('%Y_%m_%d')
    si = io.StringIO()
    si.write('\ufeff')
    cw = csv.writer(si, delimiter=';')

    if export_type == 'journal':
        filename = f"user_actions_log_{today_str}.csv"
        logs = VisitLog.query.order_by(VisitLog.created_at.desc()).all()
        
        cw.writerow(['№', 'ФИО пользователя', 'Название книги', 'Дата и время'])
        for idx, log in enumerate(logs, 1):
            fio = log.user.get_fio if log.user_id else "Неаутентифицированный пользователь"
            book_title = log.book.title if log.book else "Удаленная книга"
            date_str = log.created_at.strftime('%d.%m.%Y %H:%M:%S')
            cw.writerow([idx, fio, book_title, date_str])

    elif export_type == 'book_stats':
        filename = f"book_views_stats_{today_str}.csv"
        date_from_str = request.args.get('date_from', '')
        date_to_str = request.args.get('date_to', '')

        stats_query = db.session.query(
            Book.title,
            func.count(VisitLog.id).label('view_count')
        ).join(VisitLog, Book.id == VisitLog.book_id)\
         .filter(VisitLog.user_id.isnot(None))

        if date_from_str:
            df = datetime.strptime(date_from_str, '%Y-%m-%d')
            stats_query = stats_query.filter(VisitLog.created_at >= df)
        if date_to_str:
            dt = datetime.strptime(date_to_str, '%Y-%m-%d')
            dt = datetime.combine(dt, datetime.max.time())
            stats_query = stats_query.filter(VisitLog.created_at <= dt)

        stats_query = stats_query.group_by(Book.id).order_by(func.count(VisitLog.id).desc())
        results = stats_query.all()

        cw.writerow(['№', 'Название книги', 'Количество просмотров'])
        for idx, row in enumerate(results, 1):
            cw.writerow([idx, row[0], row[1]])
    else:
        return "Неверный тип отчета", 400

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

if __name__ == '__main__':
    # Сервер сам назначит порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)