import omni.kit.livestream.messaging as messaging
import omni.kit.app
import carb.events
import carb

ALL_OMNIVERSE_API_OBJECTS = []

class OmniverseAPI:
    ''''
    OmniverseAPI makes it easy to add API request handlers to your Kit applications

    ## Kit Python Code
    
    from ovapi import OmniverseAPI
    
    app = OmniverseAPI()

    @app.request
    def hello_world(name: str): str:
        return f"hello {name}"
    
    
    ## Web Client Code
    
    const api = new OmniverseAPI(
        streamConfig,
    );
    const response = await api?.request("hello_world", {name: "Bob"});
    console.log(`${JSON.stringify(response)}`);
    '''
    __subscriptions = {}
    __update_event_sub = None
    __signal_handlers = {}
    
    def __init__(self):
        ALL_OMNIVERSE_API_OBJECTS.append(self)
        update_stream = omni.kit.app.get_app().get_update_event_stream()
        self.__update_event_sub= update_stream.create_subscription_to_pop(self.__on_update, name=f"OvAPIUpdateSub{len(ALL_OMNIVERSE_API_OBJECTS)}")

    def __del__(self):
        self.cleanup()
        
    def __on_update(self, e: carb.events.IEvent):
        # for handler in self.__signal_handlers.values():
        #     handler(e)
        return
    
    def cleanup(self):
        for _, sub in self.__subscriptions.items():
            sub.unsubscribe()
        self.__subscriptions = {}
        for handler in self.__signal_handlers.values():
            handler.unsubscribe()
        self.__signal_handlers = {}
        self.__update_event_sub.unsubscribe()
        self.__update_event_sub = None

    def request(self, func, name: str = None):
        name = name or func.__name__
        request_name = f"{name}_request"
        response_name = f"{name}_response"
        request_event_type = carb.events.type_from_string(request_name)
        response_event_type = carb.events.type_from_string(response_name)
        # Register request handler
        app = omni.kit.app.get_app()
        stream =  app.get_message_bus_event_stream()
        def on_event(e: carb.events.IEvent):
            # Get the payload as a Python dict and remove the `id` key
            # This enables us to unpack the dict into function arguments for func, see func(**args)
            args = dict(e.payload.get_dict())
            try:
                # Handle the case that the caller didn't provide an id.
                # In this case, just return -1 for the id and the call gets to deal with it (or not)
                id = args["id"]
                del args["id"]
            except Exception:
                id = -1
            response = func(**args)
            # Only respond if we have an id to respond to
            should_respond = id != -1
            if should_respond:
                try:
                    response_payload = {"response": response, "id": id}
                except Exception as e:
                    response_payload = {"error": str(e), "id": id}
                stream.dispatch(response_event_type, payload=response_payload)
                stream.pump()
        sub = stream.create_subscription_to_pop_by_type(request_event_type, on_event, name=request_name)
        self.__subscriptions[request_name] = sub
        # Register response type
        messaging.register_event_type_to_send(response_name) 
        return func

    def signal(self, func, name: str = None):
        name = name or func.__name__
        signal_name = f"{name}_signal"
        print("signal defined")
        messaging.register_event_type_to_send(signal_name) 
        # Register request handler
        app = omni.kit.app.get_app()
        stream =  app.get_message_bus_event_stream()
        signal_event_type = carb.events.type_from_string(signal_name)
        signal_event_type_kit = carb.events.type_from_string(f"{signal_name}_kit")

        def on_signal(e: carb.events.IEvent):
            print("signal triggered")
            # Get the payload as a Python dict and remove the `id` key
            # This enables us to unpack the dict into function arguments for func, see func(**args)
            args = dict(e.payload.get_dict())
            try:
                response = func(**args)
                payload = {"signal": response}
                stream.dispatch(signal_event_type, payload=payload)
                stream.pump()
            except Exception as e:
                payload = {"error": str(e)}
                stream.dispatch(signal_event_type, payload=payload)
                stream.pump()

        sub = stream.create_subscription_to_pop_by_type(signal_event_type_kit, on_signal)
        self.__signal_handlers[signal_event_type] = sub
        # Register response type
        return func
