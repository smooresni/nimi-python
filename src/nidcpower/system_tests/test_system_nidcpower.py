import hightime
import nidcpower
import os
import pytest
import tempfile


def pytest_generate_tests(metafunc):
    '''Parametrizes the "session" fixture by examining the the markers set for a test.

    By default, the session fixture is parametrized so each test runs once with an Independent
    Channels session. To also run a test with a legacy Synchronized Channels session, decorate the
    test with the custom marker @pytest.mark.include_legacy_session. To run a test with only a
    legacy session, decorate the test with @pytest.mark.legacy_session_only.
    '''

    if 'session' in metafunc.fixturenames:
        # fixtures can't be parametrized more than once. this approach prevents exclusive
        # markers from being set on the same test

        legacy_session_only = metafunc.definition.get_closest_marker('legacy_session_only')
        include_legacy_session = metafunc.definition.get_closest_marker('include_legacy_session')

        if legacy_session_only:
            metafunc.parametrize('session', [False], indirect=True)
        if include_legacy_session:
            metafunc.parametrize('session', [True, False], indirect=True)
        if not legacy_session_only and not include_legacy_session:
            metafunc.parametrize('session', [True], indirect=True)


@pytest.fixture(scope='function')
def session(request):
    '''Creates an NI-DCPower Session.

    Markers can be used to override the default initializer arguments. For example,
    @pytest.mark.resource_name('4162/0') will override the default resource name.

    Available markers include:
        @pytest.mark.resource_name
        @pytest.mark.channels
        @pytest.mark.reset
        @pytest.mark.options
        @pytest.mark.independent_channels

    By default, all dependent tests will run once with an Independent Channels session. Dependent
    tests can override this behavior by using custom markers. Refer to the documentation in
    pytest_generate_tests for more information.
    '''

    # set default values
    init_args = {
        'resource_name': '4162',
        'channels': '',
        'reset': False,
        'options': 'Simulate=1, DriverSetup=Model:4162; BoardType:PXIe',
        'independent_channels': request.param
    }

    # iterate through markers and update arguments
    for marker in request.node.iter_markers():
        if marker.name in init_args:  # only look at markers with valid argument names
            init_args[marker.name] = marker.args[0]  # assume single parameter in marker

    # initialize and yield session
    with nidcpower.Session(**init_args) as simulated_session:
        yield simulated_session


@pytest.mark.include_legacy_session
def test_self_test(session):
    session.self_test()


@pytest.mark.include_legacy_session
def test_self_cal(session):
    session.self_cal()


def test_get_channel_name_independent_channels(session):
    name = session.get_channel_name(1)
    assert name == '4162/0'


@pytest.mark.legacy_session_only
def test_get_channel_name_synchronized_channels(session):
    name = session.get_channel_name(1)
    assert name == '0'


def test_get_channel_names_independent_channels(session):
    expected_string = ['4162/{0}'.format(x) for x in range(12)]
    channel_indices = ['0-1, 2, 3:4', 5, (6, 7), range(8, 10), slice(10, 12)]
    assert session.get_channel_names(channel_indices) == expected_string


@pytest.mark.legacy_session_only
def test_get_channel_names_synchronized_channels(session):
    expected_string = [str(x) for x in range(12)]
    channel_indices = ['0-1, 2, 3:4', 5, (6, 7), range(8, 10), slice(10, 12)]
    assert session.get_channel_names(channel_indices) == expected_string


@pytest.mark.include_legacy_session
def test_get_attribute_string(session):
    model = session.instrument_model
    assert model == 'NI PXIe-4162'


@pytest.mark.include_legacy_session
def test_error_message():
    try:
        # We pass in an invalid model name to force going to error_message
        with nidcpower.Session('4162', [0, 1], False, 'Simulate=1, DriverSetup=Model:invalid_model; BoardType:PXIe'):
            assert False
    except nidcpower.Error as e:
        assert e.code == -1074134964
        assert e.description.find('The option string parameter contains an entry with an unknown option value.') != -1


@pytest.mark.include_legacy_session
def test_get_error(session):
    try:
        session.instrument_model = ''
        assert False
    except nidcpower.Error as e:
        assert e.code == -1074135027  # Error : Attribute is read-only.
        assert e.description.find('Attribute is read-only.') != -1


@pytest.mark.include_legacy_session
def test_get_self_cal_last_date_and_time(session):
    last_cal = session.get_self_cal_last_date_and_time()
    assert last_cal.year == 1940
    assert last_cal.month == 3
    assert last_cal.day == 1
    assert last_cal.hour == 0
    assert last_cal.minute == 0


@pytest.mark.include_legacy_session
def test_get_self_cal_last_temp(session):
    temperature = session.get_self_cal_last_temp()
    assert temperature == 25.0


@pytest.mark.include_legacy_session
def test_read_current_temperature(session):
    temperature = session.read_current_temperature()
    assert temperature == 25.0


@pytest.mark.include_legacy_session
def test_reset_device(session):
    channel = session.channels['0']
    default_output_function = channel.output_function
    assert default_output_function == nidcpower.OutputFunction.DC_VOLTAGE
    channel.output_function = nidcpower.OutputFunction.DC_CURRENT
    session.reset_device()
    function_after_reset = channel.output_function
    assert function_after_reset == default_output_function


@pytest.mark.include_legacy_session
def test_reset_with_default(session):
    channel = session.channels['0']
    assert channel.aperture_time_units == nidcpower.ApertureTimeUnits.SECONDS
    channel.aperture_time_units = nidcpower.ApertureTimeUnits.POWER_LINE_CYCLES
    session.reset_with_defaults()
    assert channel.aperture_time_units == nidcpower.ApertureTimeUnits.SECONDS


@pytest.mark.include_legacy_session
def test_reset(session):
    channel = session.channels['0']
    assert channel.output_enabled is True
    channel.output_enabled = False
    session.reset()
    assert channel.output_enabled is True


@pytest.mark.include_legacy_session
def test_disable(session):
    channel = session.channels['0']
    assert channel.output_enabled is True
    session.disable()
    assert channel.output_enabled is False


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_measure(session):
    session.source_mode = nidcpower.SourceMode.SINGLE_POINT
    session.output_function = nidcpower.OutputFunction.DC_VOLTAGE
    session.voltage_level_range = 6
    session.voltage_level = 2
    with session.initiate():
        reading = session.measure(nidcpower.MeasurementTypes.VOLTAGE)
        assert session.query_in_compliance() is False
    assert reading == 2


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_query_output_state(session):
    with session.initiate():
        assert session.query_output_state(nidcpower.OutputStates.VOLTAGE) is True   # since default function is DCVolt when initiated output state for DC Volt\DC current should be True and False respectively
        assert session.query_output_state(nidcpower.OutputStates.CURRENT) is False


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_config_aperture_time(session):
    expected_default_aperture_time = 0.01666
    default_aperture_time = session.aperture_time
    assert session.aperture_time_units == nidcpower.ApertureTimeUnits.SECONDS
    default_aperture_time_in_range = abs(default_aperture_time - expected_default_aperture_time) <= max(1e-09 * max(abs(default_aperture_time), abs(expected_default_aperture_time)), 0.0)  # https://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
    assert default_aperture_time_in_range is True
    session.configure_aperture_time(5, nidcpower.ApertureTimeUnits.POWER_LINE_CYCLES)
    assert session.aperture_time_units == nidcpower.ApertureTimeUnits.POWER_LINE_CYCLES
    aperture_time = session.aperture_time
    expected_aperture_time = 5
    aperture_time_in_range = abs(aperture_time - expected_aperture_time) <= max(1e-09 * max(abs(aperture_time), abs(expected_aperture_time)), 0.0)  # https://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
    assert aperture_time_in_range is True


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_fetch_multiple(session):
    session.source_mode = nidcpower.SourceMode.SINGLE_POINT
    session.configure_aperture_time(0, nidcpower.ApertureTimeUnits.SECONDS)
    session.voltage_level = 1
    count = 10
    session.measure_when = nidcpower.MeasureWhen.AUTOMATICALLY_AFTER_SOURCE_COMPLETE
    with session.initiate():
        measurements = session.fetch_multiple(count)
        assert len(measurements) == count
        assert isinstance(measurements[1].voltage, float)
        assert isinstance(measurements[1].current, float)
        assert measurements[1].in_compliance in [True, False]
        assert measurements[1].voltage == 1.0
        assert measurements[1].current == 0.00001


@pytest.mark.include_legacy_session
def test_measure_multiple(session):
    with session.initiate():
        # session is open to all 12 channels on the device
        measurements = session.measure_multiple()
        assert len(measurements) == 12
        assert measurements[1].in_compliance is None
        assert measurements[1].voltage == 0.0
        assert measurements[1].current == 0.00001
        # now a subset of the channels
        measurements = session.channels[range(4)].measure_multiple()
        assert len(measurements) == 4
        assert measurements[1].in_compliance is None
        assert measurements[1].voltage == 0.0
        assert measurements[1].current == 0.00001


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_query_max_current_limit(session):
    max_current_limit = session.query_max_current_limit(6)
    expected_max_current_limit = 0.1  # for a simulated 4162 max current limit should be 0.1 for 6V Voltage level
    max_current_limit_in_range = abs(max_current_limit - expected_max_current_limit) <= max(1e-09 * max(abs(max_current_limit), abs(expected_max_current_limit)), 0.0)  # https://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
    assert max_current_limit_in_range is True


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_query_max_voltage_level(session):
    max_voltage_level = session.query_max_voltage_level(0.03)
    expected_max_voltage_level = 24  # for a simulated 4162 max voltage level should be 24V for 30mA current limit
    max_voltage_level_in_range = abs(max_voltage_level - expected_max_voltage_level) <= max(1e-09 * max(abs(max_voltage_level), abs(expected_max_voltage_level)), 0.0)  # https://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
    assert max_voltage_level_in_range is True


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_query_min_current_limit(session):
    min_current_limit = session.query_min_current_limit(0.03)
    expected_min_current_limit = 0.0000001  # for a simulated 4162 min_current_limit should be 1uA for 6V voltage level
    min_current_limit_in_range = abs(min_current_limit - expected_min_current_limit) <= max(1e-09 * max(abs(min_current_limit), abs(expected_min_current_limit)), 0.0)  # https://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
    assert min_current_limit_in_range is True


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_set_sequence_with_source_delays(session):
    session.set_sequence([0.1, 0.2, 0.3], [0.001, 0.002, 0.003])


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_set_sequence_with_too_many_source_delays(session):
    try:
        session.set_sequence([0.1, 0.2, 0.3], [0.001, 0.002, 0.003, 0.004])
        assert False
    except ValueError:
        pass


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_set_sequence_with_too_few_source_delays(session):
    try:
        session.set_sequence([0.1, 0.2, 0.3, 0.4], [0.001, 0.002])
        assert False
    except ValueError:
        pass


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_wait_for_event_default_timeout(session):
    with session.initiate():
        session.wait_for_event(nidcpower.Event.SOURCE_COMPLETE)


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_wait_for_event_with_timeout(session):
    with session.initiate():
        session.wait_for_event(nidcpower.Event.SOURCE_COMPLETE, hightime.timedelta(seconds=0.5))


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_commit(session):
    non_default_current_limit = 0.00021
    session.current_limit = non_default_current_limit
    session.commit()


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_import_export_buffer(session):
    test_value_1 = 1
    test_value_2 = 2
    session.voltage_level = test_value_1
    assert session.voltage_level == test_value_1
    buffer = session.export_attribute_configuration_buffer()
    session.voltage_level = test_value_2
    assert session.voltage_level == test_value_2
    session.import_attribute_configuration_buffer(buffer)
    assert session.voltage_level == test_value_1


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_import_export_file(session):
    test_value_1 = 1
    test_value_2 = 2
    temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
    # NamedTemporaryFile() returns the file already opened, so we need to close it before we can use it
    temp_file.close()
    path = temp_file.name
    session.voltage_level = test_value_1
    assert session.voltage_level == test_value_1
    session.export_attribute_configuration_file(path)
    session.voltage_level = test_value_2
    assert session.voltage_level == test_value_2
    session.import_attribute_configuration_file(path)
    assert session.voltage_level == test_value_1
    os.remove(path)


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_create_and_delete_advanced_sequence(session):
    properties_used = ['output_function', 'voltage_level']
    sequence_name = 'my_sequence'
    session.source_mode = nidcpower.SourceMode.SEQUENCE
    session.create_advanced_sequence(sequence_name=sequence_name, property_names=properties_used, set_as_active_sequence=True)
    session.create_advanced_sequence_step(set_as_active_step=True)
    assert session.active_advanced_sequence == sequence_name
    session.output_function = nidcpower.OutputFunction.DC_VOLTAGE
    session.voltage_level = 1
    session.delete_advanced_sequence(sequence_name=sequence_name)
    try:
        session.active_advanced_sequence = sequence_name
        assert False
    except nidcpower.errors.DriverError:
        pass


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_create_and_delete_advanced_sequence_bad_name(session):
    properties_used = ['output_function_bad', 'voltage_level']
    sequence_name = 'my_sequence'
    session.source_mode = nidcpower.SourceMode.SEQUENCE
    try:
        session.create_advanced_sequence(sequence_name=sequence_name, property_names=properties_used, set_as_active_sequence=True)
        assert False
    except KeyError:
        pass


@pytest.mark.channels('0')
@pytest.mark.include_legacy_session
def test_create_and_delete_advanced_sequence_bad_type(session):
    properties_used = ['unlock', 'voltage_level']
    sequence_name = 'my_sequence'
    session.source_mode = nidcpower.SourceMode.SEQUENCE
    try:
        session.create_advanced_sequence(sequence_name=sequence_name, property_names=properties_used, set_as_active_sequence=True)
        assert False
    except TypeError:
        pass


@pytest.mark.legacy_session_only
def test_send_software_edge_trigger_error(session):
    try:
        session.send_software_edge_trigger(nidcpower.SendSoftwareEdgeTriggerType.START)
        assert False
    except nidcpower.Error as e:
        assert e.code == -1074118587  # Error : Function not available in multichannel session
        assert e.description.find('The requested function is not available when multiple channels are present in the same session.') != -1


@pytest.mark.include_legacy_session
def test_get_ext_cal_last_date_and_time(session):
    print(type(session))
    last_cal = session.get_ext_cal_last_date_and_time()
    assert last_cal.year == 1940
    assert last_cal.month == 3
    assert last_cal.day == 1
    assert last_cal.hour == 0
    assert last_cal.minute == 0


@pytest.mark.include_legacy_session
def test_get_ext_cal_last_temp(session):
    temperature = session.get_ext_cal_last_temp()
    assert temperature == 25.0


@pytest.mark.include_legacy_session
def test_get_ext_cal_recommended_interval(session):
    interval = session.get_ext_cal_recommended_interval()
    assert interval.days == 365


@pytest.mark.include_legacy_session
def test_set_get_vi_int_64_attribute(session):
    session.channels['0'].active_advanced_sequence_step = 1
    read_advanced_sequence_step = session.channels['0'].active_advanced_sequence_step
    assert read_advanced_sequence_step == 1


@pytest.mark.include_legacy_session
def test_channel_format_types():
    with nidcpower.Session('4162', [0, 1], False, 'Simulate=1, DriverSetup=Model:4162; BoardType:PXIe') as simulated_session:
        assert simulated_session.channel_count == 2
    with nidcpower.Session('4162', range(2), False, 'Simulate=1, DriverSetup=Model:4162; BoardType:PXIe') as simulated_session:
        assert simulated_session.channel_count == 2
    with nidcpower.Session('4162', '0,1', False, 'Simulate=1, DriverSetup=Model:4162; BoardType:PXIe') as simulated_session:
        assert simulated_session.channel_count == 2
    with nidcpower.Session('4162', None, False, 'Simulate=1, DriverSetup=Model:4162; BoardType:PXIe') as simulated_session:
        assert simulated_session.channel_count == 12
    with nidcpower.Session(resource_name='4162', reset=False, options='Simulate=1, DriverSetup=Model:4162; BoardType:PXIe') as simulated_session:
        assert simulated_session.channel_count == 12


@pytest.mark.parametrize(
    'resource_name,channels,independent_channels',
    [
        ('Dev1', None, False),
        ('Dev1', '', False),
        ('Dev1', '0', False),
        ('Dev1', '0', True)
    ]
)
def test_init_issues_deprecation_warnings(resource_name, channels, independent_channels):
    """Tests for deprecation warnings for legacy initialization options.

    A deprecation warning should occur any time independent_channels is False or a channels
    argument is supplied.
    """
    options = {'Simulate': True, 'DriverSetup': {'Model': '4162', 'BoardType': 'PXIe'}}
    with pytest.deprecated_call() as dc:
        with nidcpower.Session(resource_name, channels, options=options, independent_channels=independent_channels):
            pass
    assert len(dc.list) == 1  # assert only 1 deprecation warning was thrown
    message = dc.list[0].message.args[0]  # grabs the deprecation warning message
    if not independent_channels:
        assert message.find('Initializing session without independent channels enabled.') != -1
    if channels and independent_channels:
        assert message.find('Attempting to initialize an independent channels session with a channels argument.') != -1


@pytest.mark.parametrize(
    'resource_name,channels',
    [
        ('Dev1', None),
        ('Dev1', ''),
        ('Dev1', '0'),
        ('Dev1', '0,1'),
        (['Dev1'], [0, 1]),
        (('Dev1',), (0, 1)),
        ('Dev1', range(2))
    ]
)
def test_init_backwards_compatibility_with_initialize_with_channels(resource_name, channels):
    """Tests that legacy sessions open without exception for valid arguments."""
    options = {'Simulate': True, 'DriverSetup': {'Model': '4162', 'BoardType': 'PXIe'}}
    with nidcpower.Session(resource_name, channels, options=options, independent_channels=False):
        pass


@pytest.mark.parametrize(
    'resource_name,channels',
    [
        ('Dev1', None),
        ('Dev1', ''),
        ('Dev1', '0'),  # backwards compatibility check
        ('Dev1', '0,1'),  # backwards compatibility check
        ('Dev1/0', None),
        ('Dev1/0', ''),
        ('Dev1/0,Dev1/1', None),
        ('Dev1/0,Dev2/1', None),
        ('Dev1/0,Dev2/1', ''),
        (['Dev1/0', 'Dev1/1'], ''),  # construct with list
        (('Dev1/0', 'Dev1/1'), ''),  # construct with tuple
        ('Dev1/0-3', None),
        ('Dev1/0:3', None)
    ]
)
def test_init_with_independent_channels(resource_name, channels):
    """Tests that independent channels sessions open without exception for valid arguments."""
    options = {'Simulate': True, 'DriverSetup': {'Model': '4162', 'BoardType': 'PXIe'}}
    with nidcpower.Session(resource_name, channels, options=options, independent_channels=True):
        pass


def test_init_raises_value_error_for_multi_instrument_resource_name_and_channels_argument():
    """Combining channels with multiple instruments is invalid.

    Tests that a value error is thrown when a multi-instrument resource name is provided with
    a channels argument. How to combine the two arguments is undefined.
    """
    options = {'Simulate': True, 'DriverSetup': {'Model': '4162', 'BoardType': 'PXIe'}}
    with pytest.raises(ValueError):
        with nidcpower.Session("Dev1,Dev2", "0", options=options, independent_channels=True):
            pass


@pytest.mark.parametrize(
    'resource_name,channels,independent_channels,expected_error_code',
    [
        ('Dev1/0', '0', True, -1074097793),  # combines to 'Dev1/0/0'
        ('Dev1/0', 'Dev1/0', False, -1074135008),
        ('Dev1/0,Dev2/0', 'Dev1/0', False, -1074135008)
    ]
)
def test_init_raises_driver_errors_for_invalid_arguments(resource_name, channels, independent_channels, expected_error_code):
    """Tests for driver errors that should occur for invalid initialization arguments."""
    options = {'Simulate': True, 'DriverSetup': {'Model': '4162', 'BoardType': 'PXIe'}}
    with pytest.raises(nidcpower.errors.DriverError) as e:
        with nidcpower.Session(resource_name, channels, options=options, independent_channels=independent_channels) as session:
            # multi-instrument resource names are valid for simulated initialize with channels
            # sessions, so we make a driver call on channels and ensure that errors
            session.channels[channels].output_function = nidcpower.OutputFunction.DC_VOLTAGE
    assert e.value.code == expected_error_code


@pytest.mark.include_legacy_session
def test_repeated_capabilities_on_method_when_all_channels_are_specified(session):
    '''Sessions should not error when specifying all channels by number.'''
    assert session.channels['0'].output_enabled is True
    session.channels['0'].output_enabled = False
    session.channels['0-11'].reset()
    assert session.channels['0'].output_enabled is True


@pytest.mark.legacy_session_only
def test_error_channel_name_not_allowed_in_obsolete_session(session):
    with pytest.raises(nidcpower.Error) as e:
        session.channels['0'].reset()
    assert e.value.code == -1074118494  # NIDCPOWER_ERROR_CHANNEL_NAME_NOT_ALLOWED_IN_OBSOLETE_SESSION
    assert e.value.description.find('The channel name string must represent all channels in the session because the session was not initialized with independent channels. To specify a subset of channels for this function, first initialize the session with independent channels.') != -1


@pytest.mark.legacy_session_only
def test_error_channel_name_not_allowed(session):
    with pytest.raises(nidcpower.Error) as e:
        session.channels['0'].instrument_model
    assert e.value.code == -1074134971  # IVI_ERROR_CHANNEL_NAME_NOT_ALLOWED
    assert e.value.description.find('The channel or repeated capability name is not allowed.') != -1


@pytest.mark.include_legacy_session
def test_repeated_capabilities_with_initiate(session):
    session.channels['0-11'].initiate()
