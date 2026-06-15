from app import app
from models import db, Role, User, Genre, Book
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        db.create_all()

        if not Role.query.first():
            role_admin = Role(name='Администратор', description='Полный доступ к системе')
            role_mod = Role(name='Модератор', description='Может редактировать книги и модерировать рецензии')
            role_user = Role(name='Пользователь', description='Может оставлять рецензии')
            db.session.add_all([role_admin, role_mod, role_user])
            db.session.commit()

            # Создаем тестовых пользователей различных ролей
            admin_user = User(
                login='admin',
                password_hash=generate_password_hash('password'),
                last_name='Админов',
                first_name='Алексей',
                middle_name='Сергеевич',
                role_id=role_admin.id
            )
            mod_user = User(
                login='moderator',
                password_hash=generate_password_hash('password'),
                last_name='Модеров',
                first_name='Михаил',
                role_id=role_mod.id
            )
            # Новый тестовый аккаунт обычного пользователя
            regular_user = User(
                login='user',
                password_hash=generate_password_hash('password'),
                last_name='Пользователев',
                first_name='Иван',
                role_id=role_user.id
            )
            db.session.add_all([admin_user, mod_user, regular_user])
            
            # Добавим жанры
            g_fantasy = Genre(name='Фантастика')
            g_det = Genre(name='Детектив')
            g_classic = Genre(name='Классика')
            db.session.add_all([g_fantasy, g_det, g_classic])
            db.session.commit()

            # Добавим парочку тестовых книг для демонстрации
            book1 = Book(
                title='Мы', 
                short_description='Антиутопия Евгения Замятина.', 
                year=1920, 
                publisher='Издательство Гржебина', 
                author='Евгений Замятин', 
                pages_count=200
            )
            book1.genres.append(g_fantasy)
            book1.genres.append(g_classic)

            book2 = Book(
                title='Приключения Шерлока Холмса', 
                short_description='Рассказы о знаменитом сыщике.', 
                year=1892, 
                publisher='George Newnes', 
                author='Артур Конан Дойл', 
                pages_count=350
            )
            book2.genres.append(g_det)

            db.session.add_all([book1, book2])
            db.session.commit()
            
            print("База данных успешно инициализирована с тестовыми данными!")
        else:
            print("База данных уже содержит данные.")

if __name__ == '__main__':
    init_db()