"""All classes and a couple of helper functions making up opus.

Opus is a way to organize and execute tasks. The client creates an instance of `Tasks` and adds all `TaskProcessor` 
implementations before adding `Task` objects. Finally, the processing is performed by calling the `process_context()` 
method of the `Tasks` instance.

Typical usage example:

```python
class MyTaskProcessor(TaskProcessor):

    def __init__(self, kind: str='MyKind', kind_versions: list=['v1',], supported_commands: list = ['apply',], logger: LoggerWrapper = LoggerWrapper()):
        super().__init__(kind, kind_versions, supported_commands, logger)

    def process_task(self, task: Task, command: str, context: str = 'default', key_value_store: KeyValueStore = KeyValueStore(), state_persistence: StatePersistence = StatePersistence()) -> KeyValueStore:
        # Your implementation here....
        pass


values = KeyValueStore()
logger = MyLogger() # Some logger you implement....
tasks = Tasks(key_value_store=values, logger=logger)
tasks.register_task_processor(processor=...)    # You processor. Add all those you implement the same way.
tasks.add_task(
    task=Task(
        kind='MyKind',
        version='v1',
        spec={...}
    )
)
tasks.process_context(command='apply', context='ANY')
```
"""

import json
import hashlib
import copy
from collections.abc import Sequence
from enum import Enum
import traceback


def keys_to_lower(data: dict):
    """Converts all keys in a dict to lower case

    Args:
        data: A python dictionary

    Returns:
        The same dictionary provided as input, but with all keys converted to lower case.
    """
    final_data = dict()
    for key in data.keys():
        if isinstance(data[key], dict):
            final_data[key.lower()] = keys_to_lower(data[key])
        else:
            final_data[key.lower()] = data[key]
    return final_data


class KeyValueStore:
    """Value store available to each task during processing for the purpose of storing values as required. Each task will therefore also have access to all other values previously stored by processed tasks.

    Attributes:
        store: A dict holding values stored by a `Task`
    """
    
    def __init__(self):
        self.store = dict()

    def save(self, key: str, value: object):
        """Saves a value with the provided key

        Args:
            key: A name of the value to store
            value: The actual value (can potentially be any type)
        """
        self.store[key] = value


class LoggerWrapper:    # pragma: no cover
    """A helper class for logging. By default all log messages regardless of level is printed to STDOUT. Can be easily extended to implement a variety of logging functions.

    Attributes:
        *any*: Determined by client. By default there are no attributes
    """

    def __init__(self):
        pass

    def info(self, message: str):
        """Emits a provided message when called at `info` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        if isinstance(message, str):
            print(message)

    def warn(self, message: str):
        """Emits a provided message when called at `warning` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        self.info(message=message)

    def warning(self, message: str):
        """Emits a provided message when called at `warning` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        self.info(message=message)

    def debug(self, message: str):
        """Emits a provided message when called at `debug` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        self.info(message=message)

    def critical(self, message: str):
        """Emits a provided message when called at `critical` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        self.info(message=message)

    def error(self, message: str):
        """Emits a provided message when called at `error` level

        Args:
            message: A string with the message to be emitted to the target log (by default, STDOUT)
        """
        self.info(message=message)


class IdentifierContext:
    """Context are slightly more complex definitions to define the constraints that will identify whether a `Task` must 
    be processed or not. The use of contexts are completely optional, but when they are used, the best practice is to 
    define contexts for every task.

    Internally, OPUS depends on the following context types:

    * `Environment`
    * `Command`

    Contexts are defined in `Task` metadata as contextual identifiers and more specifically contexts are bound to 
    specific identifiers:

    ```python
    metadata = {
        "contextualIdentifiers": [
            {
                "type": ...,
                "key": ...,
                "contexts": [
                    {
                        "type": "Environment",
                        "names": [
                            "one-environment",
                            "another-environment"
                        ]
                    }
                ]
            }
        ]
    }
    task = Task(kind='TestKind', version='v1', spec={'field1': 'value1'}, metadata=metadata, logger=self.logger)
    ```
    
    A typical use case example could be where contexts are bound to `ExecutionScope` type identifiers to discriminate 
    which tasks must be processed for which command and context combination. A realistic Infrastructure-as-Code example
    may therefore look something like the following example:

    ```python
    metadata = {
        "contextualIdentifiers": [
            {
                "type": 'ExecutionScope',
                "key": 'INCLUDE',               # Only consider processing this task if the supplied processing context
                "contexts": [                   # is one of the listed environments
                    {
                        "type": "Environment",
                        "names": [
                            "sandbox",
                            "test",
                            "prod"
                        ]
                    }
                ]
            },
            {
                "type": 'ExecutionScope',
                "key": 'EXCLUDE',               # Specifically exclude this task from being processed during "delete"
                "contexts": [                   # commands
                    {
                        "type": "Command",
                        "names": [
                            "delete"
                        ]
                    }
                ]
            }
        ]
    }
    task = Task(kind='TestKind', version='v1', spec={'field1': 'value1'}, metadata=metadata, logger=self.logger)
    ```

    Attributes:
        context_type: The type (or descriptor) of constraint as a string value
        context_name: A name of the context, as a string.
    """

    def __init__(self, context_type: str, context_name: str):
        self.context_type = context_type
        self.context_name = context_name

    def context(self)->str:
        """Retrieves a single string context

        Returns:
            A string with the type and name combination of this context
        """
        return '{}:{}'.format(
            self.context_type,
            self.context_name
        )
    
    def to_dict(self)->dict:
        """Retrieves a dictionary representation of this context

        Returns:
            A dict with the context type and name. Keys for the dict are:

            * `ContextType`
            * `ContextName`
        """
        data = dict()
        data['ContextType'] = self.context_type
        data['ContextName'] = self.context_name
        return data
    
    def __eq__(self, __value: object) -> bool:
        """Compares if another `IdentifierContext` is equal to this one

        Returns:
            Returns True if both the provided context type and name matches this context.
        """
        try:
            if __value.context_type == self.context_type and __value.context_name == self.context_name:
                return True
        except:
            pass
        return False


class IdentifierContexts(Sequence):
    """A collection of `IdentifierContext` instances. 

    Create the collection with:

    ```python
    context_collections = IdentifierContexts()
    ```

    Attributes:
        identifier_contexts: List of `IdentifierContext` instances
        unique_identifier_value: Calculated unique identifier for this collection
    """

    def __init__(self):
        self.identifier_contexts = list()
        self.unique_identifier_value = hashlib.sha256(json.dumps(self.identifier_contexts).encode('utf-8')).hexdigest()

    def add_identifier_context(self, identifier_context: IdentifierContext):
        """Adds an `IdentifierContext` to the collection

        Example:

        ```python
        context_collections = IdentifierContexts()
        context_collections.add_identifier_context(
            identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        )
        ```

        Args:
            identifier_context: An `IdentifierContext` instance
        """
        duplicates = False
        if identifier_context is None:
            return
        if isinstance(identifier_context, IdentifierContext) is False:
            return
        for existing_identifier_context in self.identifier_contexts:
            if existing_identifier_context.context_type == identifier_context.context_type and existing_identifier_context.context_name == identifier_context.context_name:
                duplicates = True
        if duplicates is False:
            self.identifier_contexts.append(identifier_context)
            self.unique_identifier_value = hashlib.sha256(json.dumps(self.to_dict()).encode('utf-8')).hexdigest()

    def is_empty(self)->bool:
        """Test if the collection is empty

         Example:

        ```python
        context_collections = IdentifierContexts()

        if context_collections.is_empty() is True:
            print('The collection is empty')        # <-- This should be printed
        else:
            print('The collection is NOT empty')

        context_collections.add_identifier_context(
            identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        )

        if context_collections.is_empty() is True:
            print('The collection is empty')
        else:
            print('The collection is NOT empty')    # <-- This should be printed
        ```

        Returns:
            Boolean value `True` of the collection has no `IdentifierContext` registered.
        """
        if len(self.identifier_contexts) > 0:
            return False
        return True
    
    def contains_identifier_context(self, target_identifier_context: IdentifierContext)->bool:
        """Check is a `IdentifierContext` exists in this collection.

        Both the type and name must match in order for the context to match.

        Example:

        ```python
        context_collections = IdentifierContexts()
        context_collections.add_identifier_context(
            identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        )

        if context_collections.contains_identifier_context(
            target_identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        ) is True:
            print('Context is part of the collection...')
        ```

        Args:
            target_identifier_context: The input `IdentifierContext` instance to test against the local collection.

        Returns:
            A boolean `True` if the local collection contains the provided `IdentifierContext` to check against
        """
        try:
            local_identifier_context: IdentifierContext
            for local_identifier_context in self.identifier_contexts:
                if local_identifier_context == target_identifier_context:
                    return True
        except: # pragma: no cover
            pass
        return False
    
    def to_dict(self)->dict:
        """Returns the collection as a Python `dict` object

        Example:

        ```python
        import json


        context_collections = IdentifierContexts()
        context_collections.add_identifier_context(
            identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        )

        print('JSON Object: {}'.format(json.dumps(context_collections.to_dict())))
        # Expected Output:
        # {
        #   "IdentifierContexts": [ 
        #       {
        #           "ContextType": "...",
        #           "ContextName": "..."
        #       }
        #   ]
        # }
        ```

        Returns:
            A dict with the key `IdentifierContexts` that has a list of contexts.
        """
        data = dict()
        data['IdentifierContexts'] = list()
        for identifier_context in self.identifier_contexts:
            data['IdentifierContexts'].append(identifier_context.to_dict())
        data['UniqueId'] = self.unique_identifier_value
        return data

    def __getitem__(self, index):
        return self.identifier_contexts[index]

    def __len__(self)->int:
        """Returns the number of contexts currently registered with this collection.

        Returns:
            An integer with the number of `IdentifierContexts` objects registered
        """
        return len(self.identifier_contexts)


class Identifier:
    """Identifiers are typically `Task` names and labels. It is useful for defining task dependencies and to calculate 
    the processing order of tasks. It is also used to determine which tasks are eligible for processing given a certain
    processing context.

    `Identifier` object are typically created from metadata of a task.

    Identifiers can be `contextual` of `non-contextual`. A non-contextual identifier is just an `Identifier` with no 
    `IdentifierContext` objects (empty `IdentifierContexts`).

    In OPUS, `non-contextual` identifiers usually have one of the following `identifier_type` values:

    * `ManifestName` - Used to define a name of a `Task`. This type only have a `key` defined
    * `Label` - Used to add labels to a `Task`. This type have both a `key` (label name) and `val` (label value) defined

    On the other hand, `contextual` identifiers can have the following types:

    * `ExecutionScope` - Usually only has a `key` with either the value `INCLUDE` or `EXCLUDE`. In addition, the contexts are usually Of the `Environment` and/or `Command` type. This Identifier is used to define the processing scope of a `Task` during task processing.

    Example of defining a `non-contextual` identifier for a `Task` name:

    ```python
    task_name_identifier = Identifier(
        identifier_type='ManifestName',
        key='task-name'
    )
    ```

    Example of defining a `non-contextual` identifier for a `Task` label:

    ```python
    task_label_identifier = Identifier(
        identifier_type='Label',
        key='label-name',
        val=';abel-value'
    )
    ```

    Example of a `contextual` identifier to specifically exclude task processing given a all scopes (given certain 
    environments and commands). In this hypothetical example, a task with this identifier will not be processed for 
    "production" environments:

    ```python
    context_collections = IdentifierContexts()
    context_collections.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Environment',
            context_name='production'
        )
    )
    context_collections.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Command',
            context_name='apply'
        )
    )
    context_collections.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Command',
            context_name='delete'
        )
    )
    context_collections.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Command',
            context_name='describe'
        )
    )
    context_collections.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Command',
            context_name='analyse'
        )
    )

    task_processing_exclusion_contextual_identifier = Identifier(
        identifier_type='ExecutionScope',
        key='EXCLUDE',
        identifier_contexts=context_collections
    )
    ```
    
    Two identifier objects can also be directly compared for equality (matches):

    ```python
    if identifier1 == identifier2:
        ...
    ```

    For `non-contextual` identifiers the type, key and val values are compared and if all matches, a boolean `True`
    value will be returned.

    For `contextual` identifiers the type, key and val values are compared and if **any** of the contexts matches, a
    boolean `True` value will be returned.

    Attributes:
        identifier_type: A string containing the type name of this identifier
        key: A string with a key.
        val: A [optional] string with a value (defaults to `None` if no value is supplied)
        identifier_contexts: An [optional] `IdentifierContexts` collection.
        unique_identifier_value: A calculated unique ID for this identifier.
        is_contextual_identifier: Calculated boolean value. True is a supplied `identifier_contexts` collections contains at least 1 `IdentifierContext` definition
    """

    def __init__(self, identifier_type: str, key: str, val: str=None, identifier_contexts: IdentifierContexts=IdentifierContexts()):
        self.identifier_type = identifier_type
        self.key = key
        self.val = val
        self.identifier_contexts = identifier_contexts
        self.unique_identifier_value = self._calc_unique_id()
        self.is_contextual_identifier = bool(len(identifier_contexts))

    def _calc_unique_id(self)->str:
        data = dict()
        data['IdentifierType'] = self.identifier_type
        data['IdentifierKey'] = self.key
        if self.val is not None:
            data['IdentifierValue'] = self.val
        data['IdentifierContexts'] = self.identifier_contexts.to_dict()
        return hashlib.sha256(json.dumps(data).encode('utf-8')).hexdigest()

    def identifier_matches_any_context(self, identifier_type: str, key: str, val: str=None, target_identifier_contexts: IdentifierContexts=IdentifierContexts())->bool:
        """If the supplied `identifier_type`, `key` and `val` values matches the values of this object, proceed to check
        if any of the the supplied `IdentifierContext` objects match the locally stored `IdentifierContexts`

        Example:

        ```python
        # Setup our identifier context collection...
        ics = IdentifierContexts()
        ics.add_identifier_context(
            identifier_context=IdentifierContext(
                context_type='...',
                context_name='...'
            )
        )

        # Create an identifier
        identifier_1 = Identifier(
            identifier_type='...',
            key='...',
            val='...',
            identifier_contexts=ics
        )

        # Create other identifiers similar to the one above:
        identifier_2 = ...
        identifier_3 = ...
        identifier_N = ...

        # Create a simple list of identifiers (this is almost the same as `Identifiers`, but simpler...):
        id_list = [
            identifier_1,
            identifier_2,
            ...
        ]

        # Create an identifier to match:
        identifier_to_test = Identifier(
            identifier_type='...',
            key='...',
            val='...',
            identifier_contexts=...
        )

        # See if it matches
        id: Identifier
        for id in id_list:
            if id.identifier_matches_any_context(
                identifier_type=identifier_to_test.identifier_type,
                key=identifier_to_test.key,
                val=identifier_to_test.val,
                target_identifier_contexts=identifier_to_test.identifier_contexts
            ) is True:
                print('Match found....')
        ```

        Args:
            identifier_type: A string containing the type name of this identifier
            key: A string with a key.
            val: A [optional] string with a value (defaults to `None` if no value is supplied)
            target_identifier_contexts: An `IdentifierContexts` collection.

        Returns:
            Boolean `True` when the following conditions are ALL met:

            * The `identifier_type` matches the object type value
            * The `key` matches the object key value
            * The `val` matches the object `val` value
            * Any of the `IdentifierContext` contained in the supplied `target_identifier_contexts` matches any one of the locally stored `IdentifierContext` objects in the locally stored `IdentifierContexts`
        """
        if self.identifier_type == identifier_type and self.key == key and self.val == val:
            if self.identifier_contexts.is_empty() is True or target_identifier_contexts.is_empty() is True:
                """This identifier (self) is not context bound or the provided target_identifier_contexts is empty, 
                therefore the contexts does not matter."""
                return True
            for target_identifier_context in target_identifier_contexts:
                if self.identifier_contexts.contains_identifier_context(target_identifier_context=target_identifier_context):
                    return True
        return False
    
    def to_dict(self)->dict:
        """Returns the collection as a Python `dict` object

        Example:

        ```python
        import json


        some_identifier = Identifier(...)

        print('JSON Object: {}'.format(json.dumps(some_identifier.to_dict())))
        # Expected Output:
        # {
        #   "IdentifierContexts": [ 
        #       {
        #           "IdentifierType": "...",
        #           "IdentifierKey": "...",
        #           "IdentifierValue": "...",
        #           "IdentifierContexts": {
        #               ...
        #           },
        #           "UniqueId": "..."
        #       }
        #   ]
        # }
        ```

        NOTE: The `IdentifierValue` field is OPTIONAL, depending if the internal value is `None` or not

        Returns:
            A dict with the key `IdentifierContexts` that has a list of contexts.
        """
        data = dict()
        data['IdentifierType'] = self.identifier_type
        data['IdentifierKey'] = self.key
        if self.val is not None:
            data['IdentifierValue'] = self.val
        data['IdentifierContexts'] = self.identifier_contexts.to_dict()
        data['UniqueId'] = self.unique_identifier_value
        return data
    
    def __eq__(self, candidate_identifier: object) -> bool:
        key_matches = False
        val_matches = False
        context_matches = False
        try:
            if candidate_identifier.identifier_type == self.identifier_type:
                if candidate_identifier.key == self.key:
                    key_matches = True
                if candidate_identifier.val == self.val:
                    val_matches = True
                if len(candidate_identifier.identifier_contexts) == 0 and len(self.identifier_contexts) == 0:
                    context_matches = True
                else:
                    candidate_context: IdentifierContext
                    for candidate_context in candidate_identifier.identifier_contexts:
                        if self.identifier_contexts.contains_identifier_context(target_identifier_context=candidate_context) is True:
                            context_matches = True
                        if key_matches is True and val_matches is True and context_matches is True:
                            return True
        except: # pragma: no cover
            pass
        if key_matches is True and val_matches is True and context_matches is True:
            return True
        return False
    

class Identifiers(Sequence):
    """A collection of `Identifier` instances.

    Helper functions exist to create the collection given a `dict` of the metadata.

    Example for `non-contextual` identifiers:

    ```python
    metadata = {
        "identifiers": [
            {
                "type": "ManifestName",
                "key": "my-name"
            },
            {
                "type": "Label",
                "key": "my-key",
                "value": "my-value"
            }
        ]
    }
    identifiers = build_non_contextual_identifiers(metadata=metadata)
    ```

    Example for `contextual` identifiers:

    ```python
    metadata = {
        "contextualIdentifiers": [
            {
                "type": "ExecutionScope",
                "key": "include",
                "contexts": [
                    {
                        "type": "environment",
                        "names": [
                            "env1",
                            "env2",
                            "env3"
                        ]
                    },
                    {
                        "type": "command",
                        "names": [
                            "cmd1",
                            "cmd2"
                        ]
                    }
                ]
            }
        ]
    }
    identifiers = build_contextual_identifiers(metadata=metadata)
    ```

    Attributes:
        identifiers: A list of `Identifier` instances
        unique_identifier_value: A hash of the combined `Identifier` instances
    """

    def __init__(self):
        self.identifiers = list()
        self.unique_identifier_value = hashlib.sha256(json.dumps(self.identifiers).encode('utf-8')).hexdigest()

    def add_identifier(self, identifier: Identifier):
        """Adds an identifier to the collections

        Args:
            identifier: An `Identifier`
        """
        can_add = True
        for existing_identifier in self.identifiers:
            if existing_identifier.to_dict()['UniqueId'] == identifier.to_dict()['UniqueId']:
                can_add = False
        if can_add is True:
            self.identifiers.append(identifier)
            self.unique_identifier_value = hashlib.sha256(json.dumps(self.to_metadata_dict()).encode('utf-8')).hexdigest()

    def identifier_found(self, identifier: Identifier)->bool:
        """Determines if a specific identifier exists in the current collection.

        Also see `Identifier` class documentation, especially on how `contextual` and `non-contextual` identifiers are 
        compared to determine a match.

        Args:
            identifier: An `Identifier` to match against the collection

        Returns:
            Boolean `True` if any of the local `Identifier` objects satisfied the equality test.
        """
        local_identifier: Identifier
        for local_identifier in self.identifiers:
            if local_identifier == identifier:
                return True
        return False

    def identifier_matches_any_context(self, identifier_type: str, key: str, val: str=None, target_identifier_contexts: IdentifierContexts=IdentifierContexts())->bool:
        for local_identifier in self.identifiers:
            if local_identifier.identifier_matches_any_context(identifier_type=identifier_type, key=key, val=val, target_identifier_contexts=target_identifier_contexts) is True:
                return True
        return False

    def to_metadata_dict(self):
        """Converts the collection to a `dict` suitable for metadata usage

        Example of `non-contextual` identifiers as a dict:

        ```yaml
        identifiers:
        - type: ManifestName
          key: my-manifest
        - type: Label
          key: my-key
          value: my-value  
        ```

        Example of `contextual` identifiers as a dict:

        ```yaml
        contextualIdentifiers:
        - type: ExecutionScope
          key: INCLUDE
          contexts:
          - type: Environment
            names:
            - sandbox
            - test
            - production
          - type: Command
            names:
            - apply
            - delete
        ```

        Returns:
            A Python `dict`
        """
        metadata = dict()
        identifier: Identifier
        for identifier in self.identifiers:
            if isinstance(identifier, Identifier):

                context_types = dict()
                item = dict()
                item['type'] = identifier.identifier_type
                item['key'] = identifier.key
                if identifier.val is not None:
                    item['val'] = identifier.val

                if identifier.is_contextual_identifier is True:
                    if 'contextualIdentifiers' not in metadata:
                        metadata['contextualIdentifiers'] = list()

                    item['contexts'] = list()
                    identifier_context: IdentifierContext
                    for identifier_context in identifier.identifier_contexts:
                        if identifier_context.context_type not in context_types:
                            context_types[identifier_context.context_type] = list()
                        context_types[identifier_context.context_type].append(identifier_context.context_name)

                    for context_type, context_names in context_types.items():
                        item['contexts'].append(
                            {
                                'type': context_type,
                                'names': context_names
                            }
                        )

                    metadata['contextualIdentifiers'].append(item)

                else:
                    if 'identifiers' not in metadata:
                        metadata['identifiers'] = list()
                    metadata['identifiers'].append(item)

        return metadata

    def __getitem__(self, index):
        return self.identifiers[index]

    def __len__(self):
        return len(self.identifiers)


class StatePersistence:
    """If the client requires any form of persistance, this class must be implemented with the required logic by the 
    client. 

    Without any client implementation, this class is mostly just a memory cache at runtime with no long term
    persistence.

    An instance of the `StatePersistence` class will be passed as a parameter to each `TaskProcessor` during processing.
    This can be useful for the task processing steps to determine the exact actions to take. Updated state could then be
    persisted long term for future task processing runs.

    Attributes:
        logger: An implementation of the `LoggerWrapper` class
        state_cache: A dict with the current state
        configuration: A dict holding configuration data, intended for use for client implementations of this class, for example DB credentials.
    """

    def __init__(self, logger: LoggerWrapper=LoggerWrapper(), configuration: dict=dict()):
        self.logger = logger
        self.state_cache = dict()
        self.configuration = configuration
        self.retrieve_all_state_from_persistence()

    def retrieve_all_state_from_persistence(self, on_failure: object=False)->bool:
        """This method must return all long term persisted state from some backend storage service, or local disc drive.

        A client must implement this method with the logic to retrieve persisted data.

        Args:
            on_failure: An object to return (or Exception to be thrown) on failure to retrieve the persisted data.

        Returns:
            A boolean to state the success (True) or the value of `on_failure`, provided the type of `on_failure` is not 
            an Exception.

            A simple example to throw an exception if the retrieval of persisted data failed:

            ```python
            p = StatePersistence(configuration={'path': '/data/persisted_data.json'})
            p.retrieve_all_state_from_persistence(on_failure=Exception('Failed to retrieve data from "{}"'.format(p.configuration['path'])))
            ```

        Raises:
            Exception: If retrieval of data failed and `on_failure` is of type `Exception`
        """
        self.logger.warning(message='StatePersistence.retrieve_all_state_from_persistence() NOT IMPLEMENTED. Override this function in your own class for long term state storage.')
        if isinstance(on_failure, Exception):
            raise on_failure
        return on_failure

    def get_object_state(self, object_identifier: str, refresh_cache_if_identifier_not_found: bool=True)->dict:
        """Retrieves state of a given identifier from the cache.

        BY default, If the key (identifier) is not found in the cache, the cache will first be refreshed and then one 
        more attempt to retrieve the value will be made.

        It is not required by the client to override this method, unless different logic is required.

        Args:
            object_identifier: The identifier of the data to retrieve. This is the same key as is provided when calling `save_object_state()` to persist data.

        Returns:
            A dict with data is returned. If no data is found, the dict will be empty.
        """
        if object_identifier in self.state_cache:
            return copy.deepcopy(self.state_cache[object_identifier])
        elif refresh_cache_if_identifier_not_found is True:
            self.retrieve_all_state_from_persistence()
            if object_identifier in self.state_cache:
                return copy.deepcopy(self.state_cache[object_identifier])
        return dict()

    def save_object_state(self, object_identifier: str, data: dict):
        """Save a dict object with a given key

        This method must ideally be overridden by the client as it needs to implement the logic of saving data long 
        term.

        When implementing the method, the current line of logic should be kept in order to refresh the local cache with
        the new data value,

        Args:
            object_identifier: The identifier of the data to retrieve.
            data: A dict with the data. The client would typically convert this to a JSON string for saving.
        """
        self.state_cache[object_identifier] = copy.deepcopy(data)

    def persist_all_state(self):
        """Save all state in one go.

        This method must ideally be overridden by the client as it needs to implement the logic of saving data long 
        term.

        The default action should the client not override this method is to loop through all items in the local cache
        and call `save_object_state()` on each one individually.
        """
        for key, data in self.state_cache.items():
            self.save_object_state(object_identifier=key, data=data)
        self.logger.warning(message='StatePersistence.persist_all_state() NOT IMPLEMENTED. Override this function in your own class for long term state storage.')


class TaskLifecycleStage(Enum):
    """An enumeration of all possible task processing life cycle stages.
    
    Attributes:
        TASK_PRE_REGISTER: stage with value of 1
        TASK_PRE_REGISTER_ERROR: stage with value of -1
        TASK_REGISTERED: stage with value of 2
        TASK_REGISTERED_ERROR: stage with value of -2
        TASK_PRE_PROCESSING_START: stage with value of 3
        TASK_PRE_PROCESSING_START_ERROR: stage with value of -3
        TASK_PRE_PROCESSING_COMPLETED: stage with value of 4
        TASK_PRE_PROCESSING_COMPLETED_ERROR: stage with value of -4
        TASK_PROCESSING_PRE_START: stage with value of 5
        TASK_PROCESSING_PRE_START_ERROR: stage with value of -5
        TASK_PROCESSING_POST_DONE: stage with value of 6
        TASK_PROCESSING_POST_DONE_ERROR: stage with value of -6
    """
    TASK_PRE_REGISTER                       = 1
    TASK_PRE_REGISTER_ERROR                 = -1
    TASK_REGISTERED                         = 2
    TASK_REGISTERED_ERROR                   = -2
    TASK_PRE_PROCESSING_START               = 3
    TASK_PRE_PROCESSING_START_ERROR         = -3
    TASK_PRE_PROCESSING_COMPLETED           = 4
    TASK_PRE_PROCESSING_COMPLETED_ERROR     = -4
    TASK_PROCESSING_PRE_START               = 5
    TASK_PROCESSING_PRE_START_ERROR         = -5
    TASK_PROCESSING_POST_DONE               = 6
    TASK_PROCESSING_POST_DONE_ERROR         = -6


def get_task_lifecycle_error_stage(stage: TaskLifecycleStage)->TaskLifecycleStage:
    """Get the error event of the corresponding stage event, assuming the stage is a normal event.

    Args:
        stage: An instance of `TaskLifecycleStage`

    Returns:
        The error version of the given stage as a `TaskLifecycleStage` instance

    Raises:
        Exception: If the input stage is already an error event, an exception will be raised.
    """
    if stage.value < 0:
        raise Exception('The provided stage is already an error stage')
    return TaskLifecycleStage(stage.value * -1)


class TaskLifecycleStages(Sequence):
    """A collection of `TaskLifecycleStage` values

    Attributes:
        stages: A list of `TaskLifecycleStage` instances
    """

    def __init__(self, init_default_stages: bool=True):
        """Initializes the collection.

        By default, the collection will include all life cycle stage values.

        Args:
          init_default_stages: [optional, default=`True`] - If a `False` is supplied, the client must add the `TaskLifecycleStage` instances with the `register_lifecycle_stage()` method.
        """
        self.stages = list()
        if init_default_stages is True:
            self.stages.append(TaskLifecycleStage.TASK_PRE_REGISTER)
            self.stages.append(TaskLifecycleStage.TASK_PRE_REGISTER_ERROR)
            self.stages.append(TaskLifecycleStage.TASK_REGISTERED)
            self.stages.append(TaskLifecycleStage.TASK_REGISTERED_ERROR)
            self.stages.append(TaskLifecycleStage.TASK_PRE_PROCESSING_START)
            self.stages.append(TaskLifecycleStage.TASK_PRE_PROCESSING_START_ERROR)
            self.stages.append(TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED)
            self.stages.append(TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED_ERROR)
            self.stages.append(TaskLifecycleStage.TASK_PROCESSING_PRE_START)
            self.stages.append(TaskLifecycleStage.TASK_PROCESSING_PRE_START_ERROR)
            self.stages.append(TaskLifecycleStage.TASK_PROCESSING_POST_DONE)
            self.stages.append(TaskLifecycleStage.TASK_PROCESSING_POST_DONE_ERROR)

    def register_lifecycle_stage(self, task_life_cycle_stage: TaskLifecycleStage):
        """Add a `TaskLifecycleStage` to the collection

        Args:
            task_life_cycle_stage: Instance of `TaskLifecycleStage`
        """
        if isinstance(task_life_cycle_stage, TaskLifecycleStage) is False:
            raise Exception('Expected a TaskLifecycleStage')
        stage: TaskLifecycleStage
        if len(self.stages) == 0:
            self.stages.append(task_life_cycle_stage)
        else:
            for stage in self.stages:
                if stage.value != task_life_cycle_stage.value:
                    self.stages.append(task_life_cycle_stage)

    def stage_registered(self, stage: TaskLifecycleStage)->bool:
        """Determines if the given stage is registered with this collection

        Args:
            stage: An instance of `TaskLifecycleStage`.

        Returns:
            Boolean `True` if the provided stage is registered with the local collection, otherwise a `False` value will 
            be returned.
        """
        match_found = False
        stored_stage: TaskLifecycleStage
        for stored_stage in self.stages:
            if stored_stage.value == stage.value:
                match_found = True
        return match_found

    def __getitem__(self, index):
        return self.stages[index]

    def __len__(self):
        return len(self.stages)


class Hook:
    """A `Hook` contains logic that must be provided by the client and the logic will be executed depending to which
    lifecycle event the hook is bounded.

    A hook is typically triggered by a lifecycle event. If a hook is registered, it is typically bound to a life cycle
    event. The same hook can be bound to multiple life cycle events if needed. Also, each life cycle event can have
    multiple hooks that will all be processed when that event triggers.

    The client must define a function that will be passed in as an argument. This function must expect the following 
    named parameters:

    * hook_name: str with the name of the hook (useful for logging, among other things)
    * task: The `Task` instance being processed. The function will have access to all task attributes and functions.,
    * key_value_store: A copy of the current `KeyValueStore` instance
    * command: String with the command being executed
    * context: String with the current context
    * task_life_cycle_stage: The triggered `TaskLifecycleStage`
    * extra_parameters: A `dict` with any additional parameters
    * logger: A logger that can be used for logging.

    Attributes:
        name: String containing the hook name
        logger: An implementation of the `LoggerWrapper` class
        commands: A list of commands for which this hook will be considered.
        contexts: A list of contexts for which this hook will be considered.
        task_life_cycle_stages: An instance of `TaskLifecycleStages` defining the `TaskLifecycleStage` events for which this hook will be registered
        function_impl: A callable object that implements the hook logic.
    """

    def __init__(
            self,
            name: str,
            commands: list,
            contexts: list,
            task_life_cycle_stages: TaskLifecycleStages,
            function_impl: object,  # callable object, like a function
            logger: LoggerWrapper=LoggerWrapper()
        ):
        """Initializes a `Hook`

        Args:
            name: String containing the hook name
            commands: A list of commands for which this hook will be considered. If the list is empty, the hook will assume it is in scope for `NOT_APPLICABLE` commands (effectively any command).
            contexts: A list of contexts for which this hook will be considered. If the list is empty, the hook will assume it is in scope for `ALL` contexts.
            task_life_cycle_stages: An instance of `TaskLifecycleStages` defining the `TaskLifecycleStage` events for which this hook will be registered
            function_impl: A callable object that implements the hook logic.
            logger: An implementation of the `LoggerWrapper` class
        """
        self.name = name
        self.logger = logger
        self.commands = commands
        self.contexts = contexts
        self.task_life_cycle_stages = task_life_cycle_stages
        self.function_impl = function_impl
        if len(commands) == 0:
            self.commands.append('NOT_APPLICABLE')
        if len(contexts) == 0:
            self.contexts.append('ALL')
        if len(commands) > 1 and 'ALL' in commands:
            self.commands = ['ALL',]
        if len(contexts) > 1 and 'ALL' in contexts:
            self.contexts = ['ALL',]
        self.commands = [x.lower() for x in self.commands]
        self.contexts = [x.lower() for x in self.contexts]

    def _command_matches(self, command: str)->bool:
        if command.lower() not in self.commands:
            if len(self.commands) == 1 and 'NOT_APPLICABLE'.lower() in self.commands:
                return True
        if command.lower() in self.commands:
            return True
        return False

    def _context_matches(self, context: str)->bool:
        if context.lower() not in self.contexts:
            if len(self.contexts) == 1 and 'ALL'.lower() in self.contexts:
                return True
        if context.lower() in self.contexts:
            return True
        return False

    def hook_exists_for_command_and_context(self, command: str, context: str)->bool:
        """Determines if a hook exists for the given command and context

        Args:
            commands: A command name
            contexts: A contexts name

        Returns:
            Boolean `True` if the Hook is matching the given command and context
        """
        return self._command_matches(command=command) and self._context_matches(context=context)
    
    def hook_exists_for_task_of_the_provided_life_cycle_events(self, life_cycle_stages_to_evaluate: TaskLifecycleStages)->bool:
        """Determines if a hook exists for the given life cycle stage event

        Args:
            life_cycle_stages_to_evaluate: An instance of `TaskLifecycleStages` containing one or more `TaskLifecycleStage` instances

        Returns:
            Boolean `True` if the any of this Hook's life cycle stages matches any one of the `TaskLifecycleStage` instances contained in `life_cycle_stages_to_evaluate`
        """
        life_cycle_stage_to_evaluate: TaskLifecycleStage
        for life_cycle_stage_to_evaluate in life_cycle_stages_to_evaluate:
            life_cycle_stage: TaskLifecycleStage
            for life_cycle_stage in self.task_life_cycle_stages:
                if life_cycle_stage.value == life_cycle_stage_to_evaluate.value:
                    return True
        return False

    def process_hook(
        self,
        command: str,
        context: str,
        task_life_cycle_stage: TaskLifecycleStage,
        key_value_store: KeyValueStore,
        task: object=None,
        task_id: str=None,
        extra_parameters:dict=dict(),
        logger: LoggerWrapper=LoggerWrapper()
    )->KeyValueStore:
        """Attempt to process the Hook within a certain lifecycle event

        A `KeyValueStore` instance is passed as a parameter and could potentially be updated. The updated 
        `KeyValueStore` will be returned.

        Args:
            commands: A command name
            contexts: A contexts name
            task_life_cycle_stage: An instance of `TaskLifecycleStage` that corresponds to the current life cycle event
            key_value_store: An instance of `KeyValueStore` that the Hook can update or add to
            task: The `Task` Object in the that triggered this event
            task_id: String containing the task_id of the `Task`. 
            extra_parameters: A Python dict that may contain additional parameters
            logger: An instance of the logger that the Hook can use for logging.

        Returns:
            An updated version of the `KeyValueStore` that was passed in as a argument

        Raises:
            Exception: When the Hook fails with an exception. The error will be logged before the exception is passed on.
        """
        final_logger = self.logger
        result = copy.deepcopy(key_value_store)
        if logger is not None:
            if isinstance(logger, LoggerWrapper):
                final_logger = logger
        if self._command_matches(command=command) is False or self._context_matches(context=context) is False:
            return copy.deepcopy(key_value_store)
        if self.task_life_cycle_stages.stage_registered(stage=task_life_cycle_stage) is False:
            return copy.deepcopy(key_value_store)
        try:
            final_logger.debug(
                'Hook "{}" executed on stage "{}" for task "{}" for command "{}" in context "{}"'.format(
                    self.name,
                    task_life_cycle_stage.name,
                    task_id,
                    command,
                    context
                )
            )
            result = self.function_impl(
                hook_name=self.name,
                task=task,
                key_value_store=copy.deepcopy(key_value_store),
                command=command,
                context=context,
                task_life_cycle_stage=task_life_cycle_stage,
                extra_parameters=extra_parameters,
                logger=self.logger
            )
            if result is None:
                result = copy.deepcopy(key_value_store)
            if isinstance(result, KeyValueStore) is False:
                result = copy.deepcopy(key_value_store)
        except Exception as e:
            traceback.print_exc()
            exception_message = 'Hook "{}" failed to execute during command "{}" in context "{}" in task life cycle stage "{}"'.format(
                self.name,
                command,
                context,
                task_life_cycle_stage
            )
            final_logger.error(exception_message)
            raise e
        return result


class Hooks:
    """A dict collection of `Hook` instances.

    To create the initial collection instance, simply initialize the class with. Then add each hook with the 
    `register_hook()` method:

    ```python
    hooks = Hooks()
    hooks.register_hook(hook=...)
    ```

    Attributes:
        hook_registrar: Dict containing hooks, index by hook name.
    """
    
    def __init__(self):
        self.hook_registrar = dict()

    def register_hook(self, hook: Hook):
        """Adds a hook to the collection, provided the hook name is not already registered.

        If the hook with the same name have previously been registered, the hook registration will be silently ignored.

        Args:
            hook: A `Hook` instance
        """
        if hook.name not in self.hook_registrar:
            self.hook_registrar[hook.name] = hook

    def _extract_stages_values(self, stages: list)->list:
        stages_values = list()
        for stage in stages:
            stage_value = copy.deepcopy(stage)
            if isinstance(stage, Enum):
                stage_value = stage.value
            elif isinstance(stage, TaskLifecycleStage):
                stage_value = stage.value
            stages_values.append(stage_value)
        return stages_values

    def _get_hooks(self, command: str, context: str, task_life_cycle_stage: TaskLifecycleStage)->list:
        hooks = list()
        hook: Hook
        for hook_name, hook in self.hook_registrar.items():
            if hook.hook_exists_for_command_and_context(command=command, context=context) is True:
                stages = TaskLifecycleStages()
                stages.register_lifecycle_stage(task_life_cycle_stage=TaskLifecycleStage(task_life_cycle_stage.value))
                if hook.hook_exists_for_task_of_the_provided_life_cycle_events(life_cycle_stages_to_evaluate=stages) is True:
                    hooks.append(hook)
        return hooks

    def process_hook(
        self,
        command: str,
        context: str,
        task_life_cycle_stage: TaskLifecycleStage,
        key_value_store: KeyValueStore,
        task: object=None,
        task_id: str=None,
        extra_parameters:dict=dict(),
        logger: LoggerWrapper=LoggerWrapper()
    )->KeyValueStore:
        """Processes a hook on a task given the command, context and current life cycle event of the task.

        First, all `Hook` instances for this particular command, context and life cycle event will be identified (in no
        particular order). Then each hook will be processed by call that hook's `process()` method, given the
        appropriate arguments.

        Should any hook processing throw an exception, and provided that the life cycle event was not already processing
        an error event, the appropriate event error hooks will be called next. Eventually the exception is passed to the
        client.

        Args:
            commands: A command name
            contexts: A contexts name
            task_life_cycle_stage: An instance of `TaskLifecycleStage` that corresponds to the current life cycle event
            key_value_store: An instance of `KeyValueStore` that the Hook can update or add to
            task: The `Task` Object in the that triggered this event
            task_id: String containing the task_id of the `Task`. 
            extra_parameters: A Python dict that may contain additional parameters
            logger: An instance of the logger that the Hook can use for logging.

        Returns:
            An updated `KeyValueStore` instance.

        Raises:
            Exception: Any exception raised by a hook will be re-raised.
        """
        hook: Hook
        hook_exception_raised = False
        for hook in self._get_hooks(command=command, context=context, task_life_cycle_stage=task_life_cycle_stage):
            logger.debug('Processing hook named "{}" for task "{}" on life cycle stage "{}"'.format(hook.name, task_id, task_life_cycle_stage.name))
            try:
                result: KeyValueStore
                result = hook.process_hook(
                    command=command,
                    context=context,
                    task_life_cycle_stage=task_life_cycle_stage,
                    key_value_store=copy.deepcopy(key_value_store),
                    task=task,
                    task_id=task_id,
                    extra_parameters=extra_parameters,
                    logger=logger
                )
                if result is not None:
                    if isinstance(result, KeyValueStore):
                        key_value_store.store = copy.deepcopy(result.store)
            except Exception as e:
                hook_exception_raised = True
                if task_life_cycle_stage.value > 0:
                    exception_message = 'Hook "{}" failed to execute during command "{}" in context "{}" in task life cycle stage "{}"'.format(
                        hook.name,
                        command,
                        context,
                        task_life_cycle_stage.name
                    )
                    logger.error(exception_message)
                    try:
                        self.key_value_store = self.process_hook(
                            command='NOT_APPLICABLE',
                            context='ALL',
                            task_life_cycle_stage=get_task_lifecycle_error_stage(stage=task_life_cycle_stage),
                            key_value_store=copy.deepcopy(self.key_value_store),
                            task=task,
                            task_id=task_id,
                            extra_parameters={'Traceback': e, 'ExceptionMessage': exception_message},
                            logger=logger
                        )
                    except:
                        traceback.print_exc()
                else:
                    logger.error('While processing an ERROR event hook, another exception occurred: {}'.format(traceback.format_exc()))
            if hook_exception_raised is True:
                raise Exception('Hook processing failed. Aborting.')
        return key_value_store
    
    def any_hook_exists(self, command: str, context: str, task_life_cycle_stage: TaskLifecycleStage)->bool:
        """Determines if any hook exists for the given command, context and life cycle event.

        Args:
            commands: A command name
            contexts: A contexts name
            task_life_cycle_stage: An instance of `TaskLifecycleStage` that corresponds to the current life cycle event

        Returns:
            Boolean `True` if any hooks were found.
        """
        hook: Hook
        for hook_name, hook in self.hook_registrar.items():
            if hook.hook_exists_for_command_and_context(command=command, context=context) is True:
                target_life_cycle_stages = TaskLifecycleStages(init_default_stages=False)
                target_life_cycle_stages.register_lifecycle_stage(task_life_cycle_stage=task_life_cycle_stage)
                if hook.hook_exists_for_task_of_the_provided_life_cycle_events(life_cycle_stages_to_evaluate=target_life_cycle_stages) is True:
                    return True
        return False


def build_non_contextual_identifiers(metadata: dict, current_identifiers: Identifiers=Identifiers())->Identifiers:
    """A helper function to create an instance of `Identifiers` containing a collections of non-contextual `Identifier`
    objects extracted from the provided metadata dict.

    A non-contextual identifier includes all data in the dict under the key `identifiers`

    An example dict of non-contextual identifiers:

    ```json
    {
        "identifiers": [
            {
                "type": "ManifestName",
                "key": "my-manifest"
            },
            {
                "type": "Label",
                "key": "my-key",
                "value": "my-value"`
            }
        ]
    }
    ```
    
    Specifically for "operarius", there are two types of non-contextual identifiers:

    * `ManifestName` which is used to define a name for a `Task`
    * `Label` which is used to define labels for a `Task`

    Any other non-contextual identifier types will also be added, but will have no meaning in "operarius" processing.

    Args:
        metadata: A dict
        current_identifiers: An instance of current `Identifiers`. Any extracted non-contextual identifies will be added to the collection and a new instance will be returned.

    Returns:
        An new instance of `Identifiers` with the extracted non-contextual identifiers added to any existing identifiers passed in by the `current_identifiers` argument.
    """
    new_identifiers = Identifiers()
    new_identifiers.identifiers = copy.deepcopy(current_identifiers.identifiers)
    new_identifiers.unique_identifier_value = copy.deepcopy(current_identifiers.unique_identifier_value)

    if 'identifiers' in metadata:
        if isinstance(metadata['identifiers'], list):
            for identifier_data in metadata['identifiers']:
                if 'type' in identifier_data and 'key' in identifier_data:
                    val = None
                    if 'val' in identifier_data:
                        val = identifier_data['val']
                    if 'value' in identifier_data:
                        val = identifier_data['value']
                    new_identifiers.add_identifier(identifier=Identifier(identifier_type=identifier_data['type'], key=identifier_data['key'], val=val))

    return new_identifiers


def build_contextual_identifiers(metadata: dict, current_identifiers: Identifiers=Identifiers())->Identifiers:
    """A helper function to create an instance of `Identifiers` containing a collections of contextual `Identifier`
    objects extracted from the provided metadata dict.

    A contextual identifier includes all data in the dict under the key `contextualIdentifiers`

    An example dict of non-contextual identifiers:

    ```json
    {
        "contextualIdentifiers": [
            {
                "type": "ExecutionScope",
                "key": "INCLUDE",
                "contexts": [
                    {
                        "type": "Environment",
                        "names": [
                            "sandbox",
                            "test",
                            "production"
                        ]
                    },
                    {
                        "type": "Command",
                        "names": [
                            "apply",
                            "delete"
                        ]
                    }
                ]
            }
        ]
    }
    ```
    
    Another more complex example where processing in different environments are included/excluded. The "INCLUDE" portion
    is bounded to both environment and command, while the "EXCLUDE" portion will exclude processing for a particular
    command, regardless of the environment. Imagine a task that can only be created and deleted, but does not support
    the concept of an update:

    ```json
    {
        "contextualIdentifiers": [
            {
                "type": "ExecutionScope",
                "key": "INCLUDE",
                "contexts": [
                    {
                        "type": "Environment",
                        "names": [
                            "sandbox",
                            "test",
                            "production"
                        ]
                    },
                    {
                        "type": "Command",
                        "names": [
                            "apply",
                            "delete"
                        ]
                    }
                ]
            },
            {
                "type": "ExecutionScope",
                "key": "EXCLUDE",
                "contexts": [
                    {
                        "type": "Command",
                        "names": [
                            "update"
                        ]
                    }
                ]
            }
        ]
    }
    ```

    > NOTE: Of course if the `TaskProcessor` does not support a particular command, it should just ignored it and
    > therefore it would not have to be specifically defined. However, there may be scenarios where this configuration
    > may be required and then this is an ideal example of how that can be accomplished in metadata.

    Specifically for "operarius", there is only one type of contextual identifier:

    * `ExecutionScope` which is used to either "INCLUDE" or "EXCLUDE" processing a `Task` based on:
        * `Environment` - An environment's exact definition is up to the client.
        * `Command` - A commands exact definition is up to the client.

    When tasks are processed, they are usually processed in the context of an environment and a command.

    Any other contextual identifier types will also be added, but will have no meaning in "operarius" processing.

    > WARNING: If both "INCLUDE" and "EXCLUDE" `ExecutionScope` contexts are defined and there are some overlap in
    > environments and commands that are present in both, the final outcome can be unpredictable. The last match will be
    > used.

    Args:
        metadata: A dict
        current_identifiers: An instance of current `Identifiers`. Any extracted non-contextual identifies will be added to the collection and a new instance will be returned.

    Returns:
        An new instance of `Identifiers` with the extracted non-contextual identifiers added to any existing identifiers passed in by the `current_identifiers` argument.
    """
    new_identifiers = Identifiers()
    new_identifiers.identifiers = copy.deepcopy(current_identifiers.identifiers)
    new_identifiers.unique_identifier_value = copy.deepcopy(current_identifiers.unique_identifier_value)

    if 'contextualIdentifiers' in metadata:
        if isinstance(metadata['contextualIdentifiers'], list):
            for contextual_identifier_data in metadata['contextualIdentifiers']:
                if 'contexts' in contextual_identifier_data:
                    contexts = IdentifierContexts()
                    for context in contextual_identifier_data['contexts']:
                        if 'type' in context and 'names' in context:
                            if isinstance(context['type'], str) is True and isinstance(context['names'], list) is True:
                                context_type = context['type']
                                for name in context['names']:
                                    contexts.add_identifier_context(
                                        identifier_context=IdentifierContext(
                                            context_type=context_type,
                                            context_name=name
                                        )
                                    )
                if 'type' in contextual_identifier_data and 'key' in contextual_identifier_data:
                    val = None
                    if 'val' in contextual_identifier_data:         # pragma: no cover
                        val = contextual_identifier_data['val']
                    if 'value' in contextual_identifier_data:       # pragma: no cover
                        val = contextual_identifier_data['value']
                    new_identifiers.add_identifier(
                        identifier=Identifier(
                            identifier_type=contextual_identifier_data['type'],
                            key=contextual_identifier_data['key'],
                            val=val,
                            identifier_contexts=contexts
                        )
                    )

    return new_identifiers


class Task:
    """Holds a specific set of parameters as defined by a `spec`. A specification is in Python `dict` format and can
    therefore include more complex parameters to be made available to the task during processing.

    A task is a basic configuration item that a `TaskProcessor` will get as input in order to process based on a
    `command` and a `context`. The content of the `Task` instance (attributes) serves as a kind of complex input
    parameters for the task processor. Additional data that help organize and orchestrate the order of operations is
    mainly defined in the task metadata,

    The primary parameters for task processing is defined in the task `spec`. The layout of the spec is dependant on the
    `TaskProcessor` implementation and it's requirements.

    Task metadata may contain the following elements:

    * (contextual) identifiers
    * non-contextual identifiers
    * Dependencies linking to other tasks by name or by identifying any task that include the defined labels.
    * Annotations, which are also useful to provide parameters for `Hook` processing.

    Below is a fairly complete hypothetical example of metadata with all possible elements defined:

    ```json
    {
        "identifiers": [
            {
                "type": "ManifestName",
                "key": "test1"
            },
        ],
        "contextualIdentifiers": [
            {
                "type": "ExecutionScope",
                "key": "INCLUDE",
                "contexts": [
                    {
                        "type": "Environment",
                        "names": [
                            "sandbox1",
                            "sandbox2"
                        ]
                    }
                ]
            }
        ],
        "dependencies": [
            {
                "identifierType": "ManifestName",
                "identifiers": [
                    { "key": "name1" },
                    { "key": "name2" },
                ]
            },
            {
                "identifierType": "Label",
                "identifiers": [
                    {
                        "key": "labelname1",
                        "value": "labelvalue1"
                    },
                ]
            }
        ],
        "annotations": {
            "name1": "...",
            "name2": "...",
        }
    }
    ```

    Attributes:
        task_can_be_persisted: A boolean value to guide the persistance implementation of `StatePersistence` if this task can be persisted. The main qualifying criteria for this flag to be True is if a `ManifestName` type non-contextual `Identifier` has been defined in the metadata. With no name, it is strictly speaking never possible to retrieve the saved manifest because there is nothing to key the manifest on.
        logger: An implementation of the `LoggerWrapper` class
        kind: Links the task to a `TaskProcessor` implementation
        version: Links the task to a compatible version of a `TaskProcessor` implementation
        metadata: The original metadata as a dict
        identifiers: An instance of `Identifiers` after the metadata is parsed.
        spec: A copy of the spec as a dict
        annotations: Extracted annotation from metadata. Looks for the key "annotations" in metadata and saves a copy of the value.
        task_dependencies: A list of dependencies as extracted from metadata.
        task_as_dict: Represents the entire `Task` definition as a dict
        task_checksum: A calculated value based mainly on the SHA256 value of the `task_as_dict`
        task_id: If the task name was defined in the metadata, the task_id will be the name, else it will be the value of `task_checksum`
    """

    def __init__(self, kind: str, version: str, spec: dict, metadata: dict=dict(), logger: LoggerWrapper=LoggerWrapper()):
        """Initializes the `Task`

        Args:
            kind: The name of the `TaskProcessor` that will have the responsibility of processing this task.
            version: A version string to assist the orchestration engine finding a suitable `TaskProcessor` implementation for this `Task`
            spec: The spec, as required by the `TaskProcessor` implementation.
            metadata: [optional] dict of metadata
            logger: [optional] An implementation of the `LoggerWrapper` class
        """
        self.task_can_be_persisted = False
        self.logger = logger
        self.kind = kind
        self.version = version
        self.metadata = dict()
        self.identifiers = build_contextual_identifiers(
            metadata=metadata,
            current_identifiers=build_non_contextual_identifiers(metadata=metadata)
        )
        if metadata is not None:
            if isinstance(metadata, dict):
                self.metadata = keys_to_lower(data=metadata)
        self.spec = dict()
        if spec is not None:
            if isinstance(spec, dict):
                self.spec = keys_to_lower(data=spec)
        self.annotations = dict()
        self.task_dependencies = list()
        self.task_as_dict = dict()
        self._register_annotations()
        self._register_dependencies()
        self.task_checksum = None
        self.task_id = self._determine_task_id()
        logger.info('Task "{}" initialized. Task checksum: {}'.format(self.task_id, self.task_checksum))

    def task_match_name(self, name: str)->bool:
        """Determines if the given name matches this task's name as (optionally) defined in metadata.

        Args:
            name: The name to match against the name of this task.

        Returns:
            Boolean `True` if the provided name matches the task name.
        """
        return self.identifiers.identifier_matches_any_context(identifier_type='ManifestName', key=name)

    def task_match_label(self, key: str, value: str)->bool:
        """Determines if the given label key and value matches any of this task's labels as (optionally) defined in metadata.

        Args:
            key: The label key to match
            value: The label value to match

        Returns:
            Boolean `True` if the provided key and value pair matches any of the task's label key and value pairs.
        """
        return self.identifiers.identifier_matches_any_context(identifier_type='Label', key=key, val=value)
    
    def task_qualifies_for_processing(self, processing_target_identifier: Identifier)->bool:
        """Determines if the task must be processed given the processing context.

        Args:
            processing_target_identifier: An `Identifier` instance describing the target processing context.

        Returns:
            Boolean `True` task is deemed in scope for given the processing context.

            By default the task is assumed to be in-scope, unless there are some criteria specifically excluding the
            task from being processed.

            Disqualifying criteria include the following (returns `False`):

            * If the provided `processing_target_identifier` contains elements specifically in the "EXCLUDE" definition of the `ExecutionScope` in the `contextualIdentifiers` metadata
            * If none of the provided "command" and/or "environment" definitions in the "INCLUDE" definition of the `ExecutionScope` in the `contextualIdentifiers` metadata matches the provided `processing_target_identifier`
        """
        qualifies = True

        # Qualify the processing_target_identifier as a valid processing type identifier
        if processing_target_identifier.identifier_type != 'ExecutionScope':
            return qualifies
        elif processing_target_identifier.key != 'processing':
            return qualifies

        # Extract processing command and processing environment
        processing_command = None
        processing_environment = None
        processing_target_context: IdentifierContext
        for processing_target_context in processing_target_identifier.identifier_contexts:
            if processing_target_context.context_type == 'Command':
                processing_command = processing_target_context.context_name
            elif processing_target_context.context_type == 'Environment':
                processing_environment = processing_target_context.context_name

        # Extract task processing rules
        candidate_identifier: Identifier
        require_command_to_qualify = False
        require_environment_to_qualify = False
        required_commands = list()
        required_environments = list()
        for candidate_identifier in self.identifiers:
            if candidate_identifier.identifier_type == processing_target_identifier.identifier_type: # ExecutionScope
                if candidate_identifier.key == 'EXCLUDE':
                    candidate_identifier_context: IdentifierContext
                    for candidate_identifier_context in candidate_identifier.identifier_contexts:
                        if candidate_identifier_context.context_type == 'Command':
                            if candidate_identifier_context.context_name == processing_command:
                                qualifies = False
                                self.logger.info('Task "{}" disqualified from processing by explicit exclusion of processing command "{}"'.format(self.task_id, processing_command))
                        elif candidate_identifier_context.context_type == 'Environment':
                            if candidate_identifier_context.context_name == processing_environment:
                                qualifies = False
                                self.logger.info('Task "{}" disqualified from processing by explicit exclusion of processing environment "{}"'.format(self.task_id, processing_environment))
                elif candidate_identifier.key == 'INCLUDE':
                    for candidate_identifier_context in candidate_identifier.identifier_contexts:
                        if candidate_identifier_context.context_type == 'Command':
                            require_command_to_qualify = True
                            required_commands.append(candidate_identifier_context.context_name)
                        elif candidate_identifier_context.context_type == 'Environment':
                            require_environment_to_qualify = True
                            required_environments.append(candidate_identifier_context.context_name)
        if qualifies is True: # Only proceed matching if qualifies is still true - no need to test if it is false
            if require_command_to_qualify is True and len(required_commands) > 0:
                if processing_command not in required_commands:
                    qualifies = False
                    self.logger.info('Task "{}" disqualified from processing because  processing command "{}" was not included in the relevant context'.format(self.task_id, processing_command))
            if require_environment_to_qualify is True and len(required_environments) > 0:
                if processing_environment not in required_environments:
                    qualifies = False
                    self.logger.info('Task "{}" disqualified from processing by environment "{}" not been defined in the relevant context'.format(self.task_id, processing_environment))

        return qualifies

    def match_name_or_label_identifier(self, identifier: Identifier)->bool:
        """Determines if the given identifier matches either the `Task` name or labels extracted from metadata.

        The input `Identifier` must be one of the following types:

        * `ExecutionScope` (also requires the identifier key to be of value "processing"), in which case the match will return the boolean value from the method `task_qualifies_for_processing()`
        * `ManifestName`
        * `Label`

        Args:
            identifier: The `Identifier` to match against the `Task` name or labels extracted from metadata

        Returns:
            Boolean `True` if any matches are found.
        """

        # Determine if this task can be processed given the processing identifier.
        if identifier.identifier_type == 'ExecutionScope' and identifier.key == 'processing':
            return self.task_qualifies_for_processing(processing_target_identifier=identifier)

        # Only process if input identifier is of a name or label type        
        if identifier.identifier_type not in ('ManifestName', 'Label',):
            return False
        
        # name or label match logic
        task_identifier: Identifier
        for task_identifier in self.identifiers:
            if task_identifier.identifier_type != 'ExecutionScope' and task_identifier.key != 'processing':

                basic_match = False
                if task_identifier.identifier_type == 'ManifestName':
                    if task_identifier.key == identifier.key:
                        basic_match = True
                elif task_identifier.identifier_type == 'Label':
                    if task_identifier.key == identifier.key and task_identifier.val == identifier.val:
                        basic_match = True

                if len(identifier.identifier_contexts) == 0:
                    return basic_match  # No need for further processing - we have at least one match
                else:
                    # If we have a basic match, and the input identifier has some context,  match at least one of the provided contexts as well in order to return true
                    if basic_match is True:
                        task_identifier_context: IdentifierContext
                        for task_identifier_context in task_identifier.identifier_contexts:
                            identifier_context: IdentifierContext
                            for identifier_context in identifier.identifier_contexts:
                                if identifier_context == task_identifier_context:
                                    return True # No need for further processing - we have at least one contextual match as well

        
        return False

    def _register_annotations(self):
        if 'annotations' not in self.metadata:                          # pragma: no cover
            return
        if self.metadata['annotations'] is None:                        # pragma: no cover
            return
        if isinstance(self.metadata['annotations'], dict) is False:     # pragma: no cover
            return
        for annotation_key, annotation_value in self.metadata['annotations'].items():
            self.annotations[annotation_key] = '{}'.format(annotation_value)

    def _dependencies_found_in_metadata(self, meta_data: dict)->list:
        if 'dependencies' not in self.metadata:                         # pragma: no cover
            return list()
        if self.metadata['dependencies'] is None:                       # pragma: no cover
            return list()
        if isinstance(self.metadata['dependencies'], list) is False:    # pragma: no cover
            return list()
        return self.metadata['dependencies']

    def _register_dependencies(self):
        for dependency in self._dependencies_found_in_metadata(meta_data=self.metadata):
            if isinstance(dependency, dict) is True:
                if 'identifierType' in dependency and 'identifiers' in dependency:
                    if dependency['identifiers'] is not None and dependency['identifierType'] is not None:
                        if isinstance(dependency['identifiers'], list) and isinstance(dependency['identifierType'], str):
                            dependency_reference_type = dependency['identifierType']
                            dependency_references = dependency['identifiers']
                            for dependency_reference in dependency_references:
                                if 'key' in dependency_reference:
                                    if dependency_reference_type == 'ManifestName':
                                        self.task_dependencies.append(
                                            Identifier(
                                                identifier_type='ManifestName',
                                                key=dependency_reference['key']
                                            )
                                        )
                                    if dependency_reference_type == 'Label':
                                        self.task_dependencies.append(
                                            Identifier(
                                                identifier_type='Label',
                                                key=dependency_reference['key'],
                                                val=dependency_reference['value']
                                            )
                                        )

    def _calculate_task_checksum(self)->str:
        data = dict()
        data['kind'] = self.kind
        data['version'] = self.version
        if len(self.metadata) > 0:
            data['metadata'] = self.metadata
        if len(self.spec) > 0:
            data['spec'] = self.spec
        self.task_as_dict = data
        return hashlib.sha256(json.dumps(data).encode('utf-8')).hexdigest()

    def _determine_task_id(self):
        task_id = self._calculate_task_checksum()
        self.task_checksum = copy.deepcopy(task_id)
        
        identifier: Identifier
        for identifier in self.identifiers:
            if len(identifier.identifier_contexts) == 0:            
                if identifier.identifier_type == 'ManifestName':
                    if identifier.key is not None:
                        if isinstance(identifier.key, str) is True:
                            if len(identifier.key) > 0:
                                task_id = copy.deepcopy(identifier.key)
                                self.task_can_be_persisted = True
        if self.task_can_be_persisted is False:
            self.logger.warning(message='Task "{}" is NOT a named task and can therefore NOT be persisted.'.format(task_id))
        return task_id
        
    def __iter__(self):
        for k,v in self.task_as_dict.items():
            yield (k, v)


class TaskProcessor:
    """Must be implemented by the client and defines the logic of `Task` processing, given the task attributes at
    runtime. Each `TaskProcessor` is identified by the `kind` and supported `version` and when each `Task` is
    registered, a check will be made to ensure a compatible `TaskProcessor` is registered for that task.

    This class is used as a base class that actual task processors will inherit.

    Attributes:
        logger: An implementation of the `LoggerWrapper` class
        kind: The kind. Any `Task` with the same kind (and matching version) may be processed with this task processor.
        versions: A list of supported versions that this task processor can process
        supported_commands: A list of supported commands that this task processor can process on matching tasks.
    """

    def __init__(self, kind: str, kind_versions: list, supported_commands: list=['apply', 'get', 'delete', 'describe'], logger: LoggerWrapper=LoggerWrapper()):
        """Initializes the `TaskProcessor`. Task processors are generally not receiving parameters when initialized, and
        therefore the client implementation of this base class must use sensible default values.

        An hypothetical example would be a `TaskProcessor` that implements the logic to retrieve a resource via an
        HTTP/HTTPS type call:

        ```python
        class HttpResource(TaskProcessor):
            def __init__(self):
                super().__init__(kind='HttpResource', kind_versions=['v1'], supported_commands=['apply', 'get', 'describe'], logger=ClientLogger())
        ```

        The client implementation of this base class must contain the suitable documentation that defines the required
        `Task` "spec".

        Args:
            kind: The kind. Any `Task` with the same kind (and matching version) may be processed with this task processor.
            versions: A list of supported versions that this task processor can process
            supported_commands: A list of supported commands that this task processor can process on matching tasks.
            logger: An implementation of the `LoggerWrapper` class
        """
        self.logger = logger
        self.kind = kind
        self.versions = kind_versions
        self.supported_commands = supported_commands

    def task_pre_processing_check(
        self,
        task: Task,
        command: str,
        context: str='default',
        key_value_store: KeyValueStore=KeyValueStore(),
        call_process_task_if_check_pass: bool=False,
        state_persistence: StatePersistence=StatePersistence(),
        hooks: Hooks=Hooks()
    )->KeyValueStore:
        """Checks if the task can be processed and then proceeds with the processing.

        Any processed task will also be registered in the `KeyValueStore` in order to avoid processing the same `Task`
        more than once.

        Args:
            task: The `Task` to process
            command: The command to be applied in the processing context
            context: A string containing the processing context
            key_value_store: An instance of the `KeyValueStore`. If none is supplied, a new instance will be created.
            call_process_task_if_check_pass: A boolean (default=False) to indicate if the processing must also be executed (which requires this value to be `True`).
            state_persistence: An implementation of `StatePersistence` that the task processor can use to retrieve previous copies of the `Task` manifest in order to determine the actions to be performed.

        Returns:
            An updated `KeyValueStore` with a record with a key made up of the `task_id`, and the input `command` and
            `context`. The value can be one of the following:

            * `1` - The task is waiting/ready to be processed
            * `2` - The task was successfully processed (only possible if `call_process_task_if_check_pass` was `True`)
            * `-1` - An attempt to process the task resulted in an Exception being raised. (only possible if `call_process_task_if_check_pass` was `True`)
        """
        task_run_id = 'PROCESSING_TASK:{}:{}:{}'.format(
            task.task_id,
            command,
            context
        )
        if task_run_id not in key_value_store.store:
            key_value_store.save(key=task_run_id, value=1)
            key_value_store = hooks.process_hook(
                command=command,
                context=context,
                task_life_cycle_stage=TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED,
                key_value_store=copy.deepcopy(key_value_store),
                task=task,
                task_id=task.task_id,
                logger=self.logger
            )
        if key_value_store.store[task_run_id] == 1:
            try:
                if call_process_task_if_check_pass is True:
                    key_value_store = hooks.process_hook(
                        command=command,
                        context=context,
                        task_life_cycle_stage=TaskLifecycleStage.TASK_PROCESSING_PRE_START,
                        key_value_store=copy.deepcopy(key_value_store),
                        task=task,
                        task_id=task.task_id,
                        logger=self.logger
                    )
                    key_value_store = self.process_task(task=task, command=command, context=context, key_value_store=copy.deepcopy(key_value_store), state_persistence=state_persistence)
                    key_value_store.store[task_run_id] = 2
                    key_value_store =  hooks.process_hook(
                        command=command,
                        context=context,
                        task_life_cycle_stage=TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED,
                        key_value_store=copy.deepcopy(key_value_store),
                        task=task,
                        task_id=task.task_id,
                        logger=self.logger
                    )
            except: # pragma: no cover
                key_value_store.store[task_run_id] = -1
                key_value_store =  hooks.process_hook(
                    command=command,
                    context=context,
                    task_life_cycle_stage=TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED_ERROR,
                    key_value_store=copy.deepcopy(key_value_store),
                    task=task,
                    task_id=task.task_id,
                    logger=self.logger
                )
        else:
            self.logger.warning(message='Appears task was already previously validated and/or executed')
        return key_value_store

    def process_task(self, task: Task, command: str, context: str='default', key_value_store: KeyValueStore=KeyValueStore(), state_persistence: StatePersistence=StatePersistence())->KeyValueStore:
        """Processes a `Task` with the given processing context.

        The client must implement the logic and will primarily work of the `Task` "spec" values which serves as
        processing parameters.

        During the processing of a `Task`, the implementation logic can also add (or even update and remove) values in
        the `KeyValueStore`. This allows other tasks to re-use data created by preceding tasks and is especially useful
        when used together with the feature of task dependencies.

        Args:
            task: The `Task` to process
            command: The command to be applied in the processing context
            context: A string containing the processing context
            key_value_store: An instance of the `KeyValueStore`. If none is supplied, a new instance will be created.
            state_persistence: An implementation of `StatePersistence` that the task processor can use to retrieve previous copies of the `Task` manifest in order to determine the actions to be performed.


        Returns:
            An updated `KeyValueStore`.

        Raises:
            Exception: As determined by the processing logic.
        """
        raise Exception('Not implemented')  # pragma: no cover


def hook_function_always_throw_exception(
    hook_name:str,
    task:Task,
    key_value_store:KeyValueStore,
    command:str,
    context:str,
    task_life_cycle_stage: TaskLifecycleStage,
    extra_parameters:dict,
    logger:LoggerWrapper
)->KeyValueStore:
    """A hook function

    THis particular function will always throw an exception and is intended as a default hook function to handle error
    events.

    Args:
        hook_name: The name of the hook
        task: An instance of a `Task`
        key_value_store: An instance of KeyValueStore,
        command: The command being issued for task processing
        context: The context of task processing
        task_life_cycle_stage: The task life cycle stage as an instance of TaskLifecycleStage
        extra_parameters: A dict with extra parameters
        logger: An implementation of the `LoggerWrapper` class for logging

    Returns:
        Normally a hook function will update `task_life_cycle_stage` and return a new copy of `TaskLifecycleStage`. 

        This function will never return anything and will always throw an exception.

    Raises:
        Exception: An exception. This particular function will always throw an exception and is intended as a catchall
        for error events/
    """
    task_id = 'unknown'
    if task is not None:
        if isinstance(task, Task):
            task_id = task.task_id
    exception_message = 'Hook "{}" forced exception on command "{}" in context "{}" for life stage "{}" in task "{}"'.format(
        hook_name,
        command,
        context,
        task_life_cycle_stage.name,
        task_id
    )
    if 'ExceptionMessage' in extra_parameters:
        logger.error(exception_message)
        exception_message = extra_parameters['ExceptionMessage']
    if 'Traceback' in extra_parameters:
        if isinstance(extra_parameters['Traceback'], Exception):
            raise extra_parameters['Traceback']
    raise Exception(exception_message)


def build_command_identifier(command: str, context: str)->Identifier:
    """A helper function for creating an `Identifier` object for a given command and context processing run.

    More specifically, an `Identifier` of type `ExecutionScope` in `processing` mode will be created.

    Args:
        command: The command to be applied in the processing context
        context: A string containing the processing context

    Returns:
        An `Identifier` instance based on the input argument values.
    """
    processing_contexts = IdentifierContexts()
    processing_contexts.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Environment',
            context_name=context
        )
    )
    processing_contexts.add_identifier_context(
        identifier_context=IdentifierContext(
            context_type='Command',
            context_name=command
        )
    )
    processing_target_identifier = Identifier(
        identifier_type='ExecutionScope',
        key='processing',
        identifier_contexts=processing_contexts
    )
    return processing_target_identifier


class Tasks:
    """The primary orchestration class that will identify classes eligible for processing given a certain `command` and 
    `context`. The pre-processing steps will identify which tasks are eligible for processing, which also resolving
    their dependencies and calculating the order of processing (dependencies are processed first).

    To create `Tasks` the basic sequence of events are as follow:

    * [Optional but recommended] The client create an appropriate `LoggerWrapper` class
    * [Optional, but recommended when dealing with multiple `Tasks` instances] Create a `KeyValueStore` instance
    * [Optional, dependant on client needs] Create `Hooks` instance and add individual `Hook` instances as needed.
    * [Optional, dependant on client needs] Create an implementation of `StatePersistence`
    * Create at least one `Tasks` instances, depending on client implementation, with the earlier created optional instances of various classes.
    * CReate all `TaskProcessor` instances and add them to the `Tasks` implementation(s) with the `register_task_processor()` method
    * Client create individual `Task` instances which are then added to the appropriate `Tasks` implementation, using the `add_task()` method
    * Finally the client cal call the `process_context()` method with the appropriate runtime processing arguments to process tasks.
    * Post processing, the `key_value_store` attribute will have the complete collection of all values defined during processing which the client can use for further processing decisions.

    During the `Tasks` instance initialization, at least one default hook to handle `ERROR` events will be handled. In
    this case, it is the `hook_function_always_throw_exception` function that will be added for each error type event
    hook. This guarantees that any error event will ultimately throw an exception that will be passed to the client.

    Attributes:
        logger: An implementation of the `LoggerWrapper` class
        tasks: A dictionary containing `Task` instances.
        task_processors_executors: A dictionary containing all `TaskProcessor` instances
        task_processor_register: A dictionary linking task processor identifiers to the actual processor implementations (for easier and more effective referencing)
        key_value_store: The `KeyValueStore` keeping all values that is shared with all hooks and tasks during processing and that is updated by tasks and hooks.
        hooks: An instance of `Hooks` containing all defined hooks.
        state_persistence: An instance of `StatePersistence` for managing persisted data
    """

    def __init__(self, logger: LoggerWrapper=LoggerWrapper(), key_value_store: KeyValueStore=KeyValueStore(), hooks: Hooks=Hooks(), state_persistence: StatePersistence=StatePersistence()):
        self.logger = logger
        self.tasks = dict()
        self.task_processors_executors = dict()
        self.task_processor_register = dict()
        self.key_value_store = key_value_store
        self.hooks = hooks
        self.state_persistence = state_persistence
        self.state_persistence.retrieve_all_state_from_persistence()
        self._register_task_registration_failure_exception_throwing_hook()

    def _register_task_registration_failure_exception_throwing_hook(self):
        for error_event_life_cycle in (
            TaskLifecycleStage.TASK_PRE_REGISTER_ERROR,
            TaskLifecycleStage.TASK_REGISTERED_ERROR,
            TaskLifecycleStage.TASK_PRE_PROCESSING_START_ERROR,
            TaskLifecycleStage.TASK_PRE_PROCESSING_COMPLETED_ERROR,
            TaskLifecycleStage.TASK_PROCESSING_PRE_START_ERROR,
            TaskLifecycleStage.TASK_PROCESSING_POST_DONE_ERROR,
        ):
            if self.hooks.any_hook_exists(command='NOT_APPLICABLE', context='ALL', task_life_cycle_stage=error_event_life_cycle) is False:
                self.hooks.register_hook(
                    hook=Hook(
                        name='DEFAULT_{}_HOOK'.format(error_event_life_cycle.name),
                        commands=['NOT_APPLICABLE',],
                        contexts=['ALL',],
                        task_life_cycle_stages=error_event_life_cycle,
                        function_impl=hook_function_always_throw_exception,
                        logger=self.logger
                    )
                )

    def add_task(self, task: Task):
        if task.task_id in self.tasks:
            raise Exception('Task with ID "{}" was already added previously. Please use the "metadata.name" attribute to identify separate (but perhaps similar) manifests.')
        self.key_value_store = self.hooks.process_hook(
            command='NOT_APPLICABLE',
            context='ALL',
            task_life_cycle_stage=TaskLifecycleStage.TASK_PRE_REGISTER,
            key_value_store=copy.deepcopy(self.key_value_store),
            task=task,
            task_id=task.task_id,
            logger=self.logger
        )
        processor_id = '{}:{}'.format(task.kind, task.version)
        if processor_id not in self.task_processor_register:
            self.key_value_store = self.hooks.process_hook(
                command='NOT_APPLICABLE',
                context='ALL',
                task_life_cycle_stage=TaskLifecycleStage.TASK_REGISTERED_ERROR,
                key_value_store=self.key_value_store,
                task=task,
                task_id='N/A',
                extra_parameters={'ExceptionMessage': 'Task kind "{}" with version "{}" has no processor registered. Ensure all task processors are registered before adding tasks.'.format(task.kind, task.version)},
                logger=self.logger
            )
        self.tasks[task.task_id] = task
        self.key_value_store = self.hooks.process_hook(
            command='NOT_APPLICABLE',
            context='ALL',
            task_life_cycle_stage=TaskLifecycleStage.TASK_REGISTERED,
            key_value_store=copy.deepcopy(self.key_value_store),
            task=task,
            task_id=task.task_id
        )

    def register_task_processor(self, processor: TaskProcessor):
        if isinstance(processor.versions, list):
            executor_id = '{}'.format(processor.kind)
            for version in processor.versions:
                executor_id = '{}:{}'.format(executor_id, version)
            self.task_processors_executors[executor_id] = processor
            for version in processor.versions:
                id = '{}:{}'.format(processor.kind, version)
                self.task_processor_register[id] = executor_id

    def find_task_by_name(self, name: str, calling_task_id: str=None)->Task:
        for task_id, candidate_task in self.tasks.items():
            process = True
            if calling_task_id is not None:
                if calling_task_id == task_id:
                    process = False
            if process is True:
                if candidate_task.task_match_name(name=name) is True:
                    return candidate_task
        return None
       
    def get_task_by_task_id(self, task_id: str)->Task:
        if task_id in self.tasks:
            return self.tasks[task_id]
        raise Exception('Task with task_id "{}" NOT FOUND'.format(task_id))

    def find_tasks_matching_identifier_and_return_list_of_task_ids(self, identifier: Identifier)->list:
        tasks_found = list()
        task_id: str
        task: Task
        for task_id, task in self.tasks.items():
            if task.match_name_or_label_identifier(identifier=identifier) is True:
                tasks_found.append(task.task_id)
        return tasks_found

    def _order_tasks(self, ordered_list: list, candidate_task: Task, processing_target_identifier: Identifier)->list:
        new_ordered_list = copy.deepcopy(ordered_list)
        task_dependency_identifier: Identifier
        for task_dependency_identifier in candidate_task.task_dependencies:
            candidate_dependant_tasks_as_list = self.find_tasks_matching_identifier_and_return_list_of_task_ids(identifier=task_dependency_identifier)
            if task_dependency_identifier.identifier_type == 'ManifestName' and len(candidate_dependant_tasks_as_list) == 0:
                raise Exception('Dependant task "{}" required, but NOT FOUND'.format(task_dependency_identifier.key))
            candidate_dependant_task_id: str
            for candidate_dependant_task_id in candidate_dependant_tasks_as_list:
                if candidate_dependant_task_id not in new_ordered_list:
                    dependant_candidate_task = self.get_task_by_task_id(task_id=candidate_dependant_task_id)
                    if dependant_candidate_task.task_qualifies_for_processing(processing_target_identifier=processing_target_identifier) is True:
                        if dependant_candidate_task not in new_ordered_list:
                            new_ordered_list.append(candidate_dependant_task_id)
                    else:
                        raise Exception('Dependant task "{}" has Task "{}" as dependency, but the dependant task is not in scope for processing - cannot proceed. Either remove the task dependency or adjust the execution scope of the dependant task.'.format(candidate_task.task_id, candidate_dependant_task_id))
        if candidate_task.task_id not in new_ordered_list:
            new_ordered_list.append(candidate_task.task_id)
        return new_ordered_list

    def calculate_current_task_order(self, processing_target_identifier: Identifier)->list:
        task_order = list()
        task_id: str
        task: Task
        for task_id, task in self.tasks.items():
            self.logger.debug('calculate_current_task_order(): Considering task "{}"'.format(task.task_id))
            if task.task_qualifies_for_processing(processing_target_identifier=processing_target_identifier) is True:
                if task.task_id not in task_order:
                    task_order = self._order_tasks(ordered_list=task_order, candidate_task=task, processing_target_identifier=processing_target_identifier)
        return task_order

    def process_context(self, command: str, context: str):
        # First, build the processing identifier object
        processing_target_identifier = build_command_identifier(command=command, context=context)

        # Determine the order based on task dependencies
        task_order = self.calculate_current_task_order(processing_target_identifier=processing_target_identifier)
        task_order = list(dict.fromkeys(task_order))    # de-duplicate
        self.logger.debug('task_order={}'.format(task_order))

        # Process tasks in order, with the available task processor registered for this task kind and version
        for task_id in task_order:
            if task_id in self.tasks:
                task = self.tasks[task_id]

                self.key_value_store = self.hooks.process_hook(
                    command=command,
                    context=context,
                    task_life_cycle_stage=TaskLifecycleStage.TASK_PRE_PROCESSING_START,
                    key_value_store=copy.deepcopy(self.key_value_store),
                    task=task,
                    task_id=task_id,
                    logger=self.logger
                )

                target_task_processor_id = '{}:{}'.format(task.kind, task.version)
                if target_task_processor_id in self.task_processor_register:
                    target_task_processor_executor_id = self.task_processor_register[target_task_processor_id]
                    if target_task_processor_executor_id in self.task_processors_executors:
                        target_task_processor_executor = self.task_processors_executors[target_task_processor_executor_id]
                        if isinstance(target_task_processor_executor, TaskProcessor):                            
                            self.key_value_store = target_task_processor_executor.task_pre_processing_check(task=task, command=command, context=context, key_value_store=copy.deepcopy(self.key_value_store), call_process_task_if_check_pass=True, state_persistence=self.state_persistence, hooks=self.hooks)
                            
                            self.state_persistence.persist_all_state()

                            self.key_value_store = self.hooks.process_hook(
                                command=command,
                                context=context,
                                task_life_cycle_stage=TaskLifecycleStage.TASK_PROCESSING_POST_DONE,
                                key_value_store=copy.deepcopy(self.key_value_store),
                                task=task,
                                task_id=task_id,
                                logger=self.logger
                            )

