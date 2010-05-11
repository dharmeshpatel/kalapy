import os, decimal

import psycopg2 as dbapi
from psycopg2.extensions import UNICODE

from rapido.db.engines import utils
from rapido.db.engines.relational import RelationalDatabase


__all__ = ('DatabaseError', 'IntegrityError', 'Database')


dbapi.extensions.register_type(UNICODE)

DatabaseError = dbapi.DatabaseError
IntegrityError = dbapi.IntegrityError


class Database(RelationalDatabase):
    
    data_types = {
        "key"       :   "SERIAL PRIMARY KEY",
        "char"      :   "VARCHAR(%(size)s)",
        "text"      :   "TEXT",
        "integer"   :   "INTEGER",
        "float"     :   "FLOAT",
        "decimal"   :   "DECIMAL",
        "boolean"   :   "BOOL",
        "datetime"  :   "TIMESTAMP",
        "binary"    :   "BLOB",
    }

    def __init__(self, name, host=None, port=None, user=None, password=None):
        super(Database, self).__init__(name, host, port, user, password)
        self.connection = None
        
    def connect(self):
        if self.connection is not None:
            return self

        conn_string = 'dbname=%s' % self.name
        if self.user:
            conn_string = '%s user=%s' % (conn_string, self.user)
        if self.password:
            conn_string = '%s password=%s' % (conn_string, self.password)
        if self.host:
            conn_string = '%s host=%s' % (conn_string, self.host)
        if self.port:
            conn_string = '%s port=%s' % (conn_string, self.port)

        self.connection = dbapi.connect(conn_string)
        self.connection.set_isolation_level(1) # make transaction transparent to all cursors
        return self

    def exists_table(self, name):
        cursor = self.cursor()
        cursor.execute("""
            SELECT relname FROM pg_class
                WHERE relkind = 'r' AND relname = %s;
            """, (name,))
        return bool(cursor.fetchone())

