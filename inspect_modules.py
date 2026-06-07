import face_recognition
import importlib
print('face_recognition:', face_recognition.__file__)
try:
    m = importlib.import_module('face_recognition_models')
    print('face_recognition_models:', m.__file__)
except Exception as e:
    print('face_recognition_models import error:', e)
import sys
print('python executable:', sys.executable)
print('sys.path sample:', sys.path[:5])
