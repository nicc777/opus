import copy
import tempfile
import string
import random
import os
from pathlib import Path

from opus.operarius import KeyValueStore, LoggerWrapper, StatePersistence, Task, TaskProcessor, Tasks


def random_string(string_length: int=16)->str:
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    random_str = ''
    while len(random_str) < string_length:
        random_str = '{}{}'.format(random_str, random.choice(chars))
    return random_str


class HelloWorldTaskProcessor(TaskProcessor):

    def __init__(self, kind: str='HelloWorld', kind_versions: list=['v1',], supported_commands: list = ['apply',], logger: LoggerWrapper = LoggerWrapper()):
        super().__init__(kind, kind_versions, supported_commands, logger)

    def process_task(self, task: Task, command: str, context: str = 'default', key_value_store: KeyValueStore = KeyValueStore(), state_persistence: StatePersistence = StatePersistence()) -> KeyValueStore:
        updated_key_Value_store = KeyValueStore()
        updated_key_Value_store.store = copy.deepcopy(key_value_store.store)
        output_file: str
        output_file = '{}{}{}.txt'.format(tempfile.gettempdir(), os.sep, random_string(string_length=32))
        if 'file' in task.spec:
            output_file = '{}'.format(task.spec['file'])
        with open(output_file, 'w') as f:
            f.write('Hello World!')
        return updated_key_Value_store
    

def main():
    tasks = Tasks()
    tasks.add_task(
        task=Task(
            kind='HelloWorld',
            version='v1',
            spec={
                'file': '{}{}{}.txt'.format(str(Path.home()), os.sep, random_string(string_length=16))
            }
        )
    )
    tasks.process_context(command='apply', context='*')


if __name__ == '__main__':
    main()
    

