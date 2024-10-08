# -*- coding: utf-8 -*-

import json
import os
import re
from os.path import join as join_path
from utils import log

def init_settings():
    """Чтение настроек обновления из конфигурационного файла settings.json.
    @return: настройки обновления в виде словаря.
    """
    settings_dict = dict()
    with open('settings.json', 'r', encoding='utf-8') as file_handle:
        # загружаем из файла данные в словарь settings_dict
        settings_dict = json.load(file_handle)
    return settings_dict


def unzip_unicode(zip_path, directory=None, remove=True):
    """Разархивирование архива с именами файлов в формате Unicode.
    @param zip_path: полный путь к архиву.
    @param directory: директория в которую разархивировать файл.
    @param remove: удалить файл после разархивирования.
    """
    import zipfile

    # По умолчанию распаковываем в текущий каталог
    unzip_dir = os.path.dirname(zip_path)
    if not directory is None:
        unzip_dir = directory

    upd_zip = zipfile.ZipFile(zip_path)
    for name in upd_zip.namelist():
        unicode_name = name.encode('utf-8').decode('utf-8').replace('/', '\\')
        dirs = os.path.dirname(join_path(unzip_dir, unicode_name))
        if dirs and not os.path.exists(dirs):
            os.makedirs(dirs)

        try:
            with open(join_path(unzip_dir, unicode_name), 'wb') as file_handle:
                file_handle.write(upd_zip.read(name))
                file_handle.close()
        except IOError as ex:
            log.error('Ошибка распаковки файла.', str(ex))
    upd_zip.close()


def update_platform(connector, settings: dict):
    """Скачивание текущей релизной версии платформы 1С.
    @param connector: коннектор к сервису 1С.
    @param settings: настройки обновления в виде словаря.
    """

    platform_settings = settings["platform"].copy()

    if platform_settings["download"] is False:
        log.info(' > Обновление платформы 1С отключено.')
        return;

    log.info(' > Начало обновления платформы 1С.')
    
    # Вычисление начальной версии, с которой начинать проверку
    check_version = platform_settings["startVersion"]
    check_version_from_dir = find_latest_version_directory(platform_settings["templatePath"]);
    if check_version_from_dir is not None:
        check_version = check_version_from_dir

    # Получение информации об обновлении платформы с сайте 1С
    upd_conf = connector.check_platform_update(check_version)
    if upd_conf is None:
        log.info(' -- Обновление для текущей версии платформы не найдено.')
        log.info(' < Обновление платформы 1С завершено.')
        return

    if upd_conf["platformVersion"] == check_version:
        log.info(' -- Текущая версия платформы является актуальной.')
        log.info(' < Обновление платформы 1С завершено.')
        return

    log.info(' -- Найдена новая версия {} платформы 1С.'.format(upd_conf["platformVersion"]))

    file_size = round(upd_conf["size"] / 1024 / 1024, 2)
    log.info(' -- Размер файла обновления: {} Мб.'.format(file_size))

    log.info(' -- Скачивания архива с платформой 1С...')
    platform_url = connector.get_platform_download_url(upd_conf["distributionUin"])
    platform_binary = connector.download_file(platform_url)
    log.info(' -- Скачивания архива с платформой 1С... Завершено!')

    log.info(' -- Сохранение архива на диск...')
    filename = "{0}.zip".format(upd_conf["platformVersion"])
    full_path = join_path(settings["platformPath"], filename)
    log.info(' -- Полный путь для сохранения: {}'.format(full_path))

    new_file = open(full_path, "wb")
    new_file.write(platform_binary)
    new_file.close()
    log.info(' -- Сохранение архива на диск... Завершено!')

    if settings["unzipFiles"]:
        log.info(' -- Распаковка архива...')
        unzip_unicode(full_path)
        log.info(' -- Распаковка архива... Завершено!')

    log.info(' < Обновление платформы 1С завершено.')


def update_configurations(connector, settings: dict):
    """Скачивание обновлений для всех конфигураций, указанных в настройке.
    @param connector: коннектор к сервису 1С.
    @param settings: настройки обновления в виде словаря.
    """
    for configuration in settings["configurations"]:
        log.info(' > Начало обновления конфигурации "{}".'.format(configuration["humanName"]))

        # Вычисление начальной версии, с которой начинать проверку
        check_version = configuration["startVersion"]

        dir_config_path = join_path(settings["templatePath"], configuration["programName"])
        check_version_from_dir = find_latest_version_directory(dir_config_path);
        if check_version_from_dir is not None:
            check_version = check_version_from_dir

        upd_conf = connector.check_conf_update(configuration["programName"], check_version, configuration["platformVersion"])
        if upd_conf is None:
            log.info(' --  Обновление для текущей версии конфигурации не найдено.')
            log.info(' < Обновление конфигурации завершено.')
            continue

        if (upd_conf["configurationVersion"] is None) or upd_conf["configurationVersion"] == check_version:
            log.info(' -- Текущая версия конфигурации является актуальной.')
            log.info(' < Обновление конфигурации завершено.')
            continue

        log.info(' -- Найдена новая версия "{}" конфигурации.'.format(upd_conf["configurationVersion"]))
        log.info(' -- Скачивание цепочки обновлений...')

        for sequence in upd_conf["upgradeSequence"]:
            download_conf = connector.get_conf_download_data(sequence, upd_conf["programVersionUin"])
            if download_conf is None:
                log.info(' ---- Не удалось скачать обновление с uid={}.'.format(sequence))
                continue

            log.info(' -- > Скачивание цепочки {}...'.format(download_conf["templatePath"]))
            file_size = round(download_conf["size"] / 1024 / 1024, 2)
            log.info(' ---- Размер файла обновления: {} Мб.'.format(file_size))

            log.info(' ---- Скачивание файла обновления...')
            conf_binary = connector.download_file(download_conf["updateFileUrl"])
            log.info(' ---- Скачивание файла обновления... Завершено!')

            log.info(' ---- Сохранение архива на диск...')
            directory_path = join_path(settings["templatePath"], configuration["programName"], 
                                       extract_version_from_path(download_conf["templatePath"]))

            os.makedirs(directory_path, exist_ok=True)
            full_path = join_path(directory_path, "1cv8.zip")
            log.info(' ---- Полный путь для сохранения: {}'.format(full_path))

            new_file = open(full_path, "wb")
            new_file.write(conf_binary)
            new_file.close()
            log.info(' ---- Сохранение архива на диск... Завершено!')

            if settings["unzipFiles"]:
                log.info(' ---- Распаковка архива...')
                unzip_unicode(full_path)
                log.info(' ---- Распаковка архива... Завершено!')

        log.info(' -- < Скачивание цепочки обновлений... Завершено!')
        log.info(' < Обновление конфигурации завершено.')

def find_latest_version_directory(directory):
    # Получаем список всех подкаталогов
    subdirectories = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
    
    # Фильтруем подкаталоги, которые соответствуют формату версии
    version_dirs = []
    for subdir in subdirectories:
        try:
            # Проверяем, что подкаталог соответствует формату версии
            version_parts = list(map(int, subdir.split('.')))
            if len(version_parts) == 4:
                version_dirs.append((version_parts, subdir))
        except ValueError:
            # Если не удалось преобразовать в число, игнорируем этот подкаталог
            continue
    
    # Если нет подходящих подкаталогов, возвращаем None
    if not version_dirs:
        return None
    
    # Находим подкаталог с максимальной версией
    latest_version_dir = max(version_dirs, key=lambda x: x[0])
    
    return latest_version_dir[1]


def extract_version_from_path(path):
    # Разделяем путь на части
    parts = path.split('\\')
    
    # Ищем последнюю часть, которая соответствует формату версии
    for part in reversed(parts):
        if re.match(r'^\d+_\d+_\d+_\d+$', part):
            # Заменяем символы "_" на "."
            version = part.replace('_', '.')
            return version
    
    # Если версия не найдена, возвращаем None
    return None