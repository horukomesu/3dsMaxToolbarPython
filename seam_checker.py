import os
import json
from math import floor
from contextlib import contextmanager
from typing import List, Tuple, Dict, Any

# Импорт pymxs с обработкой ошибок
try:
    import pymxs
    rt = pymxs.runtime
except ImportError:
    print("Ошибка: pymxs не найден. Модуль работает только в 3ds Max.")
    rt = None

# Импорт из основного модуля
try:
    import lodkitfilter
    from lodkitfilter import scene_redraw_off
except ImportError:
    print("Ошибка: lodkitfilter не найден.")
    scene_redraw_off = contextmanager(lambda: (yield))

# Константы
THRESHOLD = 0.001
THRESH2 = THRESHOLD * THRESHOLD

# Глобальные переменные для хранения результатов
_unmatched_vertices = []
_analysis_results = {}

def grid_key(pos: List[float]) -> str:
    """Создает ключ сетки для пространственного хеширования."""
    return f"{floor(pos[0]/THRESHOLD)}_{floor(pos[1]/THRESHOLD)}_{floor(pos[2]/THRESHOLD)}"

def find_unmatched_vertices(vertices_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Находит вершины без парных (несовпадающие вершины).
    
    Args:
        vertices_data: Список вершин в формате [{"obj": "name", "index": int, "pos": [x,y,z]}]
    
    Returns:
        Список несовпадающих вершин
    """
    # Создаем пространственную сетку
    grid = {}
    for v in vertices_data:
        key = grid_key(v['pos'])
        grid.setdefault(key, []).append(v)

    unmatched = []

    # Проверяем каждую вершину на наличие парной
    for v in vertices_data:
        found = False
        vx, vy, vz = v['pos']
        gx, gy, gz = floor(vx / THRESHOLD), floor(vy / THRESHOLD), floor(vz / THRESHOLD)
        
        # Проверяем соседние ячейки сетки
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for dz in [-1, 0, 1]:
                    key = f"{gx+dx}_{gy+dy}_{gz+dz}"
                    for other in grid.get(key, []):
                        if other == v:
                            continue
                        ox, oy, oz = other['pos']
                        dx2 = vx - ox
                        dy2 = vy - oy
                        dz2 = vz - oz
                        if dx2 * dx2 + dy2 * dy2 + dz2 * dz2 < THRESH2:
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
        if not found:
            unmatched.append(v)

    return unmatched

def get_boundary_vertices(obj) -> List[int]:
    """Получает индексы вершин на открытых ребрах объекта."""
    global rt
    if rt is None:
        print("Ошибка: pymxs не доступен")
        return []
    
    try:
        open_edges = rt.polyOp.getOpenEdges(obj)
        if open_edges.isEmpty:
            return []
        return list(rt.polyOp.getVertsUsingEdge(obj, open_edges))
    except Exception as e:
        print(f"Ошибка при получении граничных вершин для {obj.name}: {e}")
        return []

def export_vertices_to_json(selected_objects, visible_only=True) -> List[Dict[str, Any]]:
    """
    Экспортирует граничные вершины выбранных объектов в JSON формат.
    
    Args:
        selected_objects: Список объектов для анализа
        visible_only: Только видимые объекты
    
    Returns:
        Список вершин в JSON формате
    """
    global rt
    if rt is None:
        print("Ошибка: pymxs не доступен")
        return []
    
    vertices_data = []
    
    for obj in selected_objects:
        if not rt.isValidNode(obj):
            continue
            
        if visible_only and obj.isHidden:
            continue
            
        try:
            # Получаем граничные вершины
            boundary_verts = get_boundary_vertices(obj)
            
            for vert_index in boundary_verts:
                try:
                    # Получаем позицию вершины
                    pos = rt.polyOp.getVert(obj, vert_index)
                    vertices_data.append({
                        "obj": obj.name,
                        "index": vert_index,
                        "pos": [pos.x, pos.y, pos.z]
                    })
                except Exception as e:
                    print(f"Ошибка при получении позиции вершины {vert_index} объекта {obj.name}: {e}")
                    
        except Exception as e:
            print(f"Ошибка при обработке объекта {obj.name}: {e}")
    
    return vertices_data

def analyze_seams(selected_objects=None, visible_only=True) -> Dict[str, Any]:
    """
    Основная функция анализа швов.
    
    Args:
        selected_objects: Список объектов для анализа (None = все объекты)
        visible_only: Только видимые объекты
    
    Returns:
        Словарь с результатами анализа
    """
    global _unmatched_vertices, _analysis_results, rt
    
    if rt is None:
        return {
            "success": False,
            "error": "pymxs не доступен. Модуль работает только в 3ds Max.",
            "total_vertices": 0,
            "unmatched_count": 0,
            "objects_analyzed": 0
        }
    
    # Получаем объекты для анализа
    if selected_objects is None:
        objects_to_analyze = list(rt.objects)
    else:
        objects_to_analyze = selected_objects
    
    # Фильтруем только геометрию
    geometry_objects = [obj for obj in objects_to_analyze if rt.isValidNode(obj) and rt.superclassof(obj) == rt.GeometryClass]
    
    if not geometry_objects:
        return {
            "success": False,
            "error": "Не найдено геометрических объектов для анализа",
            "total_vertices": 0,
            "unmatched_count": 0,
            "objects_analyzed": 0
        }
    
    print(f"Анализируем {len(geometry_objects)} объектов...")
    
    # Экспортируем вершины
    vertices_data = export_vertices_to_json(geometry_objects, visible_only)
    
    if not vertices_data:
        return {
            "success": False,
            "error": "Не найдено граничных вершин для анализа",
            "total_vertices": 0,
            "unmatched_count": 0,
            "objects_analyzed": len(geometry_objects)
        }
    
    print(f"Экспортировано {len(vertices_data)} граничных вершин")
    
    # Анализируем несовпадающие вершины
    unmatched = find_unmatched_vertices(vertices_data)
    
    # Сохраняем результаты
    _unmatched_vertices = unmatched
    _analysis_results = {
        "success": True,
        "total_vertices": len(vertices_data),
        "unmatched_count": len(unmatched),
        "objects_analyzed": len(geometry_objects),
        "unmatched_vertices": unmatched
    }
    
    print(f"Найдено {len(unmatched)} несовпадающих вершин")
    
    return _analysis_results

def select_unmatched_vertices():
    """Выделяет несовпадающие вершины в 3ds Max."""
    global _unmatched_vertices, rt
    
    if rt is None:
        print("Ошибка: pymxs не доступен")
        return False
    
    if not _unmatched_vertices:
        print("Нет данных о несовпадающих вершинах. Сначала выполните анализ.")
        return False
    
    with scene_redraw_off():
        try:
            # Группируем объекты по именам
            objects_by_name = {}
            for vertex_data in _unmatched_vertices:
                obj_name = vertex_data['obj']
                if obj_name not in objects_by_name:
                    objects_by_name[obj_name] = []
                objects_by_name[obj_name].append(vertex_data['index'])
            
            # Выделяем вершины для каждого объекта
            for obj_name, vertex_indices in objects_by_name.items():
                obj = rt.getNodeByName(obj_name)
                if not obj or not rt.isValidNode(obj):
                    continue
                
                try:
                    # Создаем набор индексов вершин
                    vert_set = rt.BitArray()
                    for idx in vertex_indices:
                        vert_set[idx] = True
                    
                    # Выделяем вершины
                    rt.polyOp.setVertSelection(obj, vert_set)
                    
                except Exception as e:
                    print(f"Ошибка при выделении вершин объекта {obj_name}: {e}")
            
            # Переключаемся в режим редактирования вершин
            rt.setCommandPanelTaskMode(rt.name('modify'))
            rt.subObjectLevel = 1
            
            print(f"Выделено {len(_unmatched_vertices)} несовпадающих вершин")
            return True
            
        except Exception as e:
            print(f"Ошибка при выделении вершин: {e}")
            return False

def get_analysis_summary() -> str:
    """Возвращает текстовое резюме результатов анализа."""
    global _analysis_results
    
    if not _analysis_results or not _analysis_results.get('success'):
        return "Анализ не выполнен"
    
    results = _analysis_results
    return (f"Анализ завершен:\n"
            f"Объектов проанализировано: {results['objects_analyzed']}\n"
            f"Граничных вершин найдено: {results['total_vertices']}\n"
            f"Несовпадающих вершин: {results['unmatched_count']}")

def get_unmatched_objects_list() -> List[str]:
    """Возвращает список объектов с несовпадающими вершинами."""
    global _unmatched_vertices
    
    if not _unmatched_vertices:
        return []
    
    objects_set = set()
    for vertex_data in _unmatched_vertices:
        objects_set.add(vertex_data['obj'])
    
    return sorted(list(objects_set))

def clear_analysis_results():
    """Очищает результаты предыдущего анализа."""
    global _unmatched_vertices, _analysis_results
    _unmatched_vertices = []
    _analysis_results = {}

# Функции для интеграции с UI
def run_seam_analysis(visible_only=True):
    """Запускает анализ швов с текущими настройками."""
    return analyze_seams(visible_only=visible_only)

def select_problem_vertices():
    """Выделяет проблемные вершины в сцене."""
    return select_unmatched_vertices()

def get_analysis_status() -> Dict[str, Any]:
    """Возвращает текущий статус анализа."""
    global _analysis_results
    return _analysis_results.copy() if _analysis_results else {} 