"""This module defines field classes to define relationship like many-to-one,
one-to-one, many-to-one and many-to-many between models.
"""


from _fields import Field
from _model import get_model, get_models, Model
from _errors import FieldError, DuplicateFieldError


__all__ = ('ManyToOne', 'OneToOne', 'OneToMany', 'ManyToMany')


class IRelation(Field):
    """This class defines an interface method prepare which will called
    once all defined models are loaded. So the field would have chance
    to resolve early lookup references.
    """

    def __init__(self, reference, **kw):
        super(IRelation, self).__init__(**kw)
        self._reference = reference

    def prepare(self, model_class):
        """The relation field should implement this method to implement
        support code as at this point all the models will be resolved.
        """
        pass

    @property
    def reference(self):
        """Returns the reference class.
        """
        return get_model(self._reference, self.model_class._meta.package)


class ManyToOne(IRelation):
    """ManyToOne field represents many-to-one relationship with other model.

    For example, a ManyToOne field defined in model A that refers to model B forms
    a many-to-one relationship from A to B. Every instance of B refers to a single
    instance of A and every instance of A can have many instances of B that refer
    it.

    A reverse lookup field will be automatically created in the reference model.
    In this case, a field `a_set` of type `OneToMany` will be automatically created
    on class B referencing class A.
    """

    _data_type = 'integer'

    def __init__(self, reference, reverse_name=None, cascade=False, **kw):
        """Create a new ManyToOne field referencing the given `reference` model.

        A reverse lookup field of type OneToMany will be created on the referenced
        model if it doesn't exist.

        Args:
            reference: reference model class
            reverse_name: name of the reverse lookup field in the referenced model
            cascade: None = set null, False = restrict and True = cascade
            **kw: other field params
        """
        super(ManyToOne, self).__init__(reference, **kw)
        self.reverse_name = reverse_name
        self.cascade = cascade

    def prepare(self, model_class, reverse_name=None, reverse_class=None):

        if not self.reverse_name:
            self.reverse_name = reverse_name or ('%s_set' % model_class.__name__.lower())

        if hasattr(self.reference, self.reverse_name):
            try:
                if getattr(self.reference, self.reverse_name).reverse_name == self.name:
                    return
            except:
                pass
            raise DuplicateFieldError('field %r already defined in referenced model %r' % (
                self.reverse_name, self.reference.__name__))

        c = reverse_class or OneToMany
        f = c(model_class, name=self.reverse_name, reverse_name=self.name)
        self.reference._meta.add_field(f)

    def __get__(self, model_instance, model_class):
        return super(ManyToOne, self).__get__(model_instance, model_class)
        
    def __set__(self, model_instance, value):
        if value is not None and not isinstance(value, self.reference):
            raise ValueError("ManyToOne field %r value should be an instance of %r" % (
                self.name, self._reference.__name__))
        super(ManyToOne, self).__set__(model_instance, value)

    def to_database_value(self, model_instance):
        value = super(ManyToOne, self).to_database_value(model_instance)
        if isinstance(value, Model):
            return value.key
        return value

    def from_database_value(self, model_instance, value):
        if value is not None:
            return self.reference.get(value)
        return value


class OneToOne(ManyToOne):
    """OneToOne is basically ManyToOne with unique constraint.
    """
    def __init__(self, reference, reverse_name=None, cascade=False, **kw):
        kw['unique'] = True
        super(OneToOne, self).__init__(reference, reverse_name, cascade, **kw)

    def prepare(self, model_class):
        super(OneToOne, self).prepare(model_class, 
                reverse_name=model_class.__name__.lower(),
                reverse_class=O2ORel)

class O2ORel(Field):
    """OneToOne reverse lookup field to prevent recursive
    dependencies.
    """
    def __init__(self, reference, reverse_name, **kw):
        super(O2ORel, self).__init__(**kw)
        self.reference = reference
        self.reverse_name = reverse_name

    def __get__(self, model_instance, model_class):
        return self.reference.filter('%s == :key' % self.reverse_name,
                key=model_instance.key).fetch(1)[0]

    def __set__(self, model_instance, value):
        if not isinstance(value, self.reference):
            raise TypeError('Expected %r instance' % (self.reference._meta.name))
        setattr(value, self.reverse_name, model_instance)

class O2MSet(object):
    """A descriptor class to access OneToMany fields.
    """

    def __init__(self, field, instance):
        self.__field = field
        self.__obj = instance
        self.__ref = field.reference
        self.__ref_field = getattr(field.reference, field.reverse_name)

    def all(self):
        """Returns a `Query` object pre-filtered to return related objects.
        """
        return self.__ref.filter('%s == :key' % (self.__field.reverse_name),
                key=self.__obj.key)

    def add(self, *objs):
        """Add new instances to the reference set.

        Raises:
            TypeError: if any given object is not an instance of referenced model
        """
        for obj in objs:
            if not isinstance(obj, self.__ref):
                raise TypeError('%r instance expected.' % self.__ref._meta.name)
            setattr(obj, self.__field.reverse_name, self.__obj)
            obj.save()

    def remove(self, *objs):
        """Removes the provided instances from the reference set.
        
        Raises:
            FieldError: if referenced instance field is required field.
            TypeError: if any given object is not an instance of referenced model
        """
        if self.__ref_field.required:
            raise FieldError("objects can't be removed from %r, delete the objects instead." % (
                self.__field.name))
        for obj in objs:
            if not isinstance(obj, self.__ref):
                raise TypeError('%r instances expected.' % self.__ref._meta.name)
        from rapido.db.engines import database
        database.delete_from_keys(self.__ref, [obj.key for obj in objs if obj.key])

    def clear(self):
        """Removes all referenced instances from the reference set.

        Raises:
            FieldError: if referenced instance field is required field.
            TypeError: if any given object is not an instance of referenced model
        """
        if self.__ref_field.required:
            raise FieldError("objects can't be removed from %r, \
                    delete the objects instead." % (
                self.__field.name))

        # instead of removing records at once remove them in bunches
        l = 100
        q = self.all()
        result = q.fetch(l)
        while result:
            self.remove(*result)
            result = q.fetch(l)


class M2MSet(object):
    """A descriptor class to access ManyToMany field.
    """

    def __init__(self, field, instance):
        self.__field = field
        self.__obj = instance
        self.__ref = field.reference
        self.__m2m = field.m2m

        if not instance.key:
            raise ValueError(
                    'Instance must be saved before using ManyToMany field.')

    def all(self):
        """Returns a `Query` object pre-filtered to return related objects.
        """
        return self.__m2m.filter('source == :key', key=self.__obj.key)

    def add(self, *objs):
        """Add new instances to the reference set.

        Raises:
            TypeError: if any given object is not an instance of referenced model
            ValueError: if any of the given object is not saved
        """
        for obj in objs:
            if not isinstance(obj, self.__ref):
                raise TypeError('%s instances required' % (self.__ref._meta.name))
            if not obj.key:
                raise ValueError('%r instances must me saved before using with ManyToMany field %r' % (
                    obj._meta.name, self.__field.name))

        existing = self.all().filter('target in :keys', keys=[obj.key for obj in objs]).fetch(-1)
        existing = [o.key for o in existing]

        for obj in objs:
            if obj.key in existing:
                continue
            m2m = self.__m2m()
            m2m.source = self.__obj
            m2m.target = obj
            m2m.save()

    def remove(self, *objs):
        """Removes the provided instances from the reference set.
        
        Raises:
            TypeError: if any given object is not an instance of referenced model
        """
        for obj in objs:
            if not isinstance(obj, self.__ref):
                raise TypeError('%s instances required' % (self.__ref._meta.name))

        existing = self.all().filter('target in :keys', keys=[obj.key for obj in objs]).fetch(-1)
        keys = [o.key for o in existing]

        from rapido.db.engines import database
        database.delete_from_keys(self.__m2m, keys)

    def clear(self):
        """Removes all referenced instances from the reference set.
        """
        # instead of removing records at once remove them in bunches
        l = 100
        q = self.all()
        result = q.fetch(l)
        while result:
            self.remove(*result)
            result = q.fetch(l)


class OneToMany(IRelation):
    """OneToMany field represents one-to-many relationship with other model.

    For example, a OneToMany field defined in model A that refers to model B forms
    a one-to-many relationship from A to B. Every instance of B refers to a single
    instance of A and every instance of A can have many instances of B that refer
    it.

    A reverse lookup field will be automatically created in the reference model.
    In this case, a field `a` of type `ManyToOne` will be automatically created
    on class B referencing class A.
    """

    _data_type = None

    def __init__(self, reference, reverse_name=None, **kw):
        super(OneToMany, self).__init__(reference, **kw)
        self.reverse_name = reverse_name

    def prepare(self, model_class):

        if not self.reverse_name:
            self.reverse_name = model_class.__name__.lower()
        
        if hasattr(self.reference, self.reverse_name):
            try:
                if getattr(self.reference, self.reverse_name).reverse_name == self.name:
                    return
            except:
                pass
            raise DuplicateFieldError('field %r already defined in referenced model %r' % (
                self.reverse_name, self.reference.__name__))

        f = ManyToOne(model_class, self.name, name=self.reverse_name)
        self.reference._meta.add_field(f)

    def __get__(self, model_instance, model_class):
        if model_instance is None:
            return self
        return O2MSet(self, model_instance)

    def __set__(self, model_instance, value):
        raise ValueError("Field %r is readonly." % self.name)


class ManyToMany(IRelation):
    """ManyToMany field represents many-to-many relationship with other model.

    For example, a ManyToMany field defined in model A that refers to model B
    forms a many-to-many relationship from A to B. Every instance of A can have
    many instances of B referenced by an intermediary model that also refers
    model A.

    Removing an instance of B from M2MSet will delete instances of the 
    intermediary model and thus breaking the many-to-many relationship.
    """

    _data_type = None

    def __init__(self, reference, **kw):
        super(ManyToMany, self).__init__(reference, **kw)

    def prepare(self, model_class):

        from _model import ModelType, Model

        #create intermediary model

        name = '%s_%s' % (model_class.__name__.lower(), self.name)

        @classmethod
        def _from_db_values(cls, values):
            obj = super(cls, cls)._from_db_values(values)
            return obj.target

        cls = ModelType(name, (Model,), {
            '__module__': model_class.__module__,
            '_from_db_values': _from_db_values,
        })

        cls._meta.add_field(ManyToOne(model_class, name='source'))
        cls._meta.add_field(ManyToOne(self.reference, name='target'))

        cls._meta.ref_models = [model_class, self.reference]

        #XXX: create reverse lookup fields?
        #cls.source.prepare(cls)
        #cls.target.prepare(cls)

        self.m2m = cls

    def __get__(self, model_instance, model_class):
        if model_instance is None:
            return self
        return M2MSet(self, model_instance)

    def __set__(self, model_instance, value):
        raise ValueError('Field %r is read-only' % (self.name))

