from muesli.models import *
from pyramid.security import Allow, Deny, Everyone, Authenticated, DENY_ALL, ALL_PERMISSIONS
from pyramid.httpexceptions import HTTPNotFound, HTTPForbidden

from muesli.utils import editAllTutorials, editOwnTutorials, editNoTutorials

def getTutorials(request):
	"""returns tutorials and tutorial_ids for this request.
	Does also a check whether the tutorials belong to the same lecture."""
	tutorial_ids = request.matchdict.get('tutorial_ids', request.matchdict.get('tutorial_id', '')).split(',')
	if len(tutorial_ids)==1 and tutorial_ids[0]=='':
		tutorial_ids = []
		tutorials = []
	else:
		tutorials = request.db.query(Tutorial).filter(Tutorial.id.in_(tutorial_ids)).all()
	checkTutorials(tutorials)
	return tutorials, tutorial_ids

def checkTutorials(tutorials):
	if tutorials:
		lecture_id = tutorials[0].lecture_id
		for tutorial in tutorials:
			if tutorial.lecture_id != lecture_id:
				raise HTTPForbidden('Tutorials belong to different lectures!')

def getTutorForTutorials(tutorials):
	if tutorials:
		tutorlist = [set([tutorial.tutor]) for tutorial in tutorials if tutorial.tutor]
		if tutorlist:
			tutors = set.intersection(*tutorlist)
			return tutors
		else:
			return []
	else:
		return []

class UserContext(object):
	def __init__(self, request):
		user_id = request.matchdict['user_id']
		self.user = request.db.query(User).get(user_id)
		if self.user is None:
			raise HTTPNotFound(detail='User not found')
		self.__acl__ = [
			(Allow, 'user:{0}'.format(user_id), ('view')),
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]

class ConfirmationContext(object):
	def __init__(self, request):
		confirmation_hash = request.matchdict['confirmation']
		self.confirmation = request.db.query(Confirmation).get(confirmation_hash)
		if self.confirmation is None:
			raise HTTPNotFound(detail='Confirmation not found')
		self.__acl__ = [
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]

class GeneralContext(object):
	def __init__(self, request):
		self.__acl__ = [
			(Allow, Authenticated, ('update', 'change_email', 'change_password')),
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[(Allow, 'user:{0}'.format(a.id), 'create_lecture') for a in request.db.query(User).filter(User.is_assistant==1).all()]

class GradingContext(object):
	def __init__(self, request):
		grading_id = request.matchdict['grading_id']
		self.grading = request.db.query(Grading).get(grading_id)
		if self.grading is None:
			raise HTTPNotFound(detail='Grading not found')
		self.__acl__ = [
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[(Allow, 'user:{0}'.format(assistant.id), ('view', 'edit')) for assistant in self.grading.lecture.assistants]


class LectureContext(object):
	def __init__(self, request):
		lecture_id = request.matchdict['lecture_id']
		self.lecture = request.db.query(Lecture).get(lecture_id)
		if self.lecture is None:
			raise HTTPNotFound(detail='Lecture not found')
		self.__acl__ = [
			(Allow, Authenticated, ('view', 'view_own_points', 'add_tutor')),
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[(Allow, 'user:{0}'.format(assistant.id), ('view', 'edit','change_assistant', 'view_tutorials', 'get_tutorials', 'mail_tutors')) for assistant in self.lecture.assistants
			]+[(Allow, 'user:{0}'.format(tutor.id), ('view', 'take_tutorial', 'view_tutorials', 'get_tutorials', 'mail_tutors')) for tutor in self.lecture.tutors]

class TutorialContext(object):
	def __init__(self, request):
		self.tutorial_ids_str = request.matchdict.get('tutorial_ids', request.matchdict.get('tutorial_id', ''))
		self.tutorials, self.tutorial_ids = getTutorials(request)
		if self.tutorials:
			self.lecture = self.tutorials[0].lecture
		else:
			lecture_id = request.matchdict.get('lecture_id', None)
			if lecture_id:
				self.lecture = request.db.query(Lecture).get(lecture_id)
			else:
				self.lecture = None
		self.__acl__ = [
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]
		if self.lecture:
			self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('viewOverview', 'take_tutorial')) for tutor in self.lecture.tutors]
			self.__acl__ += [((Allow, 'user:{0}'.format(assistant.id), ('viewOverview', 'viewAll', 'sendMail', 'edit', 'remove_student'))) for assistant in self.lecture.assistants]
		if self.tutorials:
			if self.lecture.tutor_rights == editOwnTutorials:
				self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('viewAll', 'remove_student')) for tutor in getTutorForTutorials(self.tutorials)]
			elif self.lecture.tutor_rights == editNoTutorials:
				#TODO: This has to be a bug?!
				self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('viewAll', 'remove_student')) for tutor in getTutorForTutorials(self.tutorials)]
			elif self.lecture.tutor_rights == editAllTutorials:
				self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('viewAll', 'remove_student')) for tutor in self.lecture.tutors]
			else: raise ValueError('Tutorrights %s not known' % self.lecture.tutor_rights)
			for tutor in getTutorForTutorials(self.tutorials):
				self.__acl__.append((Allow, 'user:{0}'.format(tutor.id), ('sendMail')))
			if self.tutorials[0].lecture.mode == 'direct':
				self.__acl__.append((Allow, Authenticated, ('subscribe')))
			if self.tutorials[0].lecture.mode in ['direct', 'off']:
				self.__acl__.append((Allow, Authenticated, ('unsubscribe')))

class AssignStudentContext(object):
	def __init__(self, request):
		student_id = request.POST['student']
		tutorial_id = request.POST['new_tutorial']
		self.student = request.db.query(User).get(student_id)
		self.tutorial = request.db.query(Tutorial).get(tutorial_id)
		if self.student is None:
			raise HTTPNotFound(detail='Student not found')
		if self.tutorial is None:
			raise HTTPNotFound(detail='tutorial not found')
		self.__acl__ = [
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[
				(Allow, 'user:{0}'.format(assistant.id), ('move')) for assistant in self.tutorial.lecture.assistants
			]


class ExamContext(object):
	def __init__(self, request):
		exam_id = request.matchdict['exam_id']
		self.exam = request.db.query(Exam).get(exam_id)
		if self.exam is None:
			raise HTTPNotFound(detail='Exam not found')
		self.tutorial_ids_str = request.matchdict.get('tutorial_ids', '')
		self.tutorials, self.tutorial_ids =  getTutorials(request)
		self.__acl__ = [
			#(Allow, Authenticated, 'view_own_points'),
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[(Allow, 'user:{0}'.format(tutor.id), ('statistics')) for tutor in self.exam.lecture.tutors
			]+[(Allow, 'user:{0}'.format(assistant.id), ('edit', 'view_points', 'enter_points', 'statistics')) for assistant in self.exam.lecture.assistants
			]
		if self.exam.lecture.tutor_rights == editAllTutorials:
			self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('enter_points', 'view_points')) for tutor in self.exam.lecture.tutors]
		else:
			if self.tutorials:
				if self.exam.lecture.tutor_rights == editOwnTutorials:
					self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('view_points', 'enter_points')) for tutor in getTutorForTutorials(self.tutorials)]
				elif self.exam.lecture.tutor_rights == editNoTutorials:
					self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('view_points')) for tutor in getTutorForTutorials(self.tutorials)]
				elif self.exam.lecture.tutor_rights == editAllTutorials:
					self.__acl__ += [(Allow, 'user:{0}'.format(tutor.id), ('view_points', 'enter_points')) for tutor in self.exam.lecture.tutors]
				else: raise ValueError('Tutorrights %s not known' % self.exam.lecture.tutor_rights)

class ExerciseContext(object):
	def __init__(self, request):
		exercise_id = request.matchdict['exercise_id']
		self.exercise = request.db.query(Exercise).get(exercise_id)
		if self.exercise is None:
			raise HTTPNotFound(detail='Exercise not found')
		self.exam = self.exercise.exam
		if 'tutorial_ids' in request.matchdict:
			self.tutorial_ids = request.matchdict['tutorial_ids'].split(',')
			if len(self.tutorial_ids)==1 and self.tutorial_ids[0]=='':
				self.tutorial_ids = []
				self.tutorials = []
			else:
				self.tutorials = request.db.query(Tutorial).filter(Tutorial.id.in_(self.tutorial_ids)).all()
		self.__acl__ = [
			(Allow, Authenticated, 'view_points'),
			(Allow, 'group:administrators', ALL_PERMISSIONS),
			]+[(Allow, 'user:{0}'.format(tutor.id), ('statistics')) for tutor in self.exam.lecture.tutors
			]+[(Allow, 'user:{0}'.format(assistant.id), ('statistics')) for assistant in self.exam.lecture.assistants
			]

class CorrelationContext(object):
	def __init__(self, request):
		source1 = request.GET['source1']
		source2 = request.GET['source2']
		ids1 = self.get_allowed_ids(source1, request)
		ids2 = self.get_allowed_ids(source2, request)
		ids = set(ids1).intersection(set(ids2))
		self.__acl__ = [
			(Allow, 'group:administrators', ALL_PERMISSIONS)
			] + [(Allow, 'user:{0}'.format(id), ('correlation')) for id in ids]
	def get_allowed_ids(self, source, request):
		source_type, source_id = source.split('_',1)
		if source_type == 'exam':
			exam = request.db.query(Exam).get(source_id)
			if exam:
				return [assistant.id for assistant in exam.lecture.assistants]+[tutor.id for tutor in exam.lecture.tutors]
			else:
				raise HTTPNotFound('Exam not found')
		elif source_type == 'lecture':
			lecture = request.db.query(Lecture).get(source_id)
			if lecture:
				return [assistant.id for assistant in lecture.assistants]+[tutor.id for tutor in lecture.tutors]
			else:
				raise HTTPNotFound('Lecture not found')
		else:
			raise ValueError('Sourcetype not known: %s' % source_type)
