#!/usr/bin/env python
#########################################################################################
#
# Register anatomical image to the template using the spinal cord centerline/segmentation.
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2013 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Benjamin De Leener, Julien Cohen-Adad, Augustin Roux
#
# About the license: see the file LICENSE.TXT
#########################################################################################

# TODO: for -ref subject, crop data, otherwise registration is too long
# TODO: testing script for all cases

import os
import shutil
import sys
import time

import msct_image
import msct_parser
import msct_register_landmarks
import sct_crop_image
import sct_label_utils
import sct_register_multimodal
import sct_utils as sct
import sct_warp_template


class Param(object):
    def __init__(self):
        self.path_sct = os.environ.get('SCT_DIR')
        self.debug = 0
        self.remove_temp_files = 1  # remove temporary files
        self.fname_mask = ''  # this field is needed in the function register@sct_register_multimodal
        self.padding = 10  # this field is needed in the function register@sct_register_multimodal
        self.verbose = 1  # verbose
        self.path_template = self.path_sct + '/data/PAM50'
        self.path_qc = os.path.abspath(os.curdir) + '/qc/'
        self.zsubsample = '0.25'
        self.param_straighten = ''


def get_parser(paramreg):
    param = Param()
    parser = msct_parser.Parser(__file__)
    parser.usage.set_description('Register anatomical image to the template.')
    parser.add_option(
        name="-i",
        type_value="file",
        description="Anatomical image.",
        mandatory=True,
        example="anat.nii.gz")
    parser.add_option(
        name="-s",
        type_value="file",
        description="Spinal cord segmentation.",
        mandatory=True,
        example="anat_seg.nii.gz")
    parser.add_option(
        name="-l",
        type_value="file",
        description="Labels. See: http://sourceforge.net/p/spinalcordtoolbox/wiki/create_labels/",
        mandatory=True,
        default_value='',
        example="anat_labels.nii.gz")
    parser.add_option(
        name="-ofolder",
        type_value="folder_creation",
        description="Output folder.",
        mandatory=False,
        default_value='')
    parser.add_option(
        name="-t",
        type_value="folder",
        description="Path to template.",
        mandatory=False,
        default_value=param.path_template)
    parser.add_option(
        name='-c',
        type_value='multiple_choice',
        description='Contrast to use for registration.',
        mandatory=False,
        default_value='t2',
        example=['t1', 't2', 't2s'])
    parser.add_option(
        name='-ref',
        type_value='multiple_choice',
        description='Reference for registration: template: subject->template, subject: template->subject.',
        mandatory=False,
        default_value='template',
        example=['template', 'subject'])
    parser.add_option(
        name="-param",
        type_value=[[':'], 'str'],
        description='Parameters for registration (see sct_register_multimodal). Default: \
                      \n--\nstep=0\ntype=' + paramreg.steps['0'].type +
        '\ndof=' + paramreg.steps['0'].dof + '\
                      \n--\nstep=1\ntype=' + paramreg.steps['1'].type +
        '\nalgo=' + paramreg.steps['1'].algo + '\nmetric=' +
        paramreg.steps['1'].metric + '\niter=' + paramreg.steps['1'].iter +
        '\nsmooth=' + paramreg.steps['1'].smooth + '\ngradStep=' +
        paramreg.steps['1'].gradStep + '\nslicewise=' + paramreg.steps['1']
        .slicewise + '\nsmoothWarpXY=' + paramreg.steps['1'].smoothWarpXY +
        '\npca_eigenratio_th=' + paramreg.steps['1'].pca_eigenratio_th + '\
                      \n--\nstep=2\ntype=' + paramreg.steps['2'].type +
        '\nalgo=' + paramreg.steps['2'].algo + '\nmetric=' +
        paramreg.steps['2'].metric + '\niter=' + paramreg.steps['2'].iter +
        '\nsmooth=' + paramreg.steps['2'].smooth + '\ngradStep=' +
        paramreg.steps['2'].gradStep + '\nslicewise=' + paramreg.steps['2']
        .slicewise + '\nsmoothWarpXY=' + paramreg.steps['2'].smoothWarpXY +
        '\npca_eigenratio_th=' + paramreg.steps['1'].pca_eigenratio_th,
        mandatory=False)
    parser.add_option(
        name="-param-straighten",
        type_value='str',
        description="""Parameters for straightening (see sct_straighten_spinalcord).""",
        mandatory=False,
        default_value='')
    parser.add_option(
        name="-r",
        type_value="multiple_choice",
        description="""Remove temporary files.""",
        mandatory=False,
        default_value='1',
        example=['0', '1'])
    parser.add_option(
        name="-v",
        type_value="multiple_choice",
        description="""Verbose. 0: nothing. 1: basic. 2: extended.""",
        mandatory=False,
        default_value=param.verbose,
        example=['0', '1', '2'])

    return parser


def initMultiStep():
    # Note: step0 is used as pre-registration
    # if ref=template, we only need translations and z-scaling because the cord is already straight
    step0 = sct_register_multimodal.Paramreg(step='0', type='label', dof='Tx_Ty_Tz_Sz')
    step1 = sct_register_multimodal.Paramreg(step='1', type='seg', algo='centermassrot', smooth='2')
    step2 = sct_register_multimodal.Paramreg(
        step='2',
        type='seg',
        algo='bsplinesyn',
        metric='MeanSquares',
        iter='3',
        smooth='1')
    return sct_register_multimodal.ParamregMultiStep([step0, step1, step2])


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    else:
        script_name =os.path.splitext(os.path.basename(__file__))[0]
        sct.printv('{0} {1}'.format(script_name, " ".join(args)))

    paramreg = initMultiStep()
    parser = get_parser(paramreg)
    param = Param()

    arguments = parser.parse(args)

    # get arguments
    fname_data = arguments['-i']
    fname_seg = arguments['-s']
    fname_landmarks = arguments['-l']
    if '-ofolder' in arguments:
        path_output = arguments['-ofolder']
    else:
        path_output = ''
    path_template = sct.slash_at_the_end(arguments['-t'], 1)
    contrast_template = arguments['-c']
    ref = arguments['-ref']
    remove_temp_files = int(arguments['-r'])
    verbose = int(arguments['-v'])
    param.verbose = verbose  # TODO: not clean, unify verbose or param.verbose in code, but not both
    if '-param-straighten' in arguments:
        param.param_straighten = arguments['-param-straighten']
    # registration parameters
    if '-param' in arguments:
        # reset parameters but keep step=0 (might be overwritten if user specified step=0)
        paramreg = sct_register_multimodal.ParamregMultiStep([paramreg.steps['0']])
        if ref == 'subject':
            paramreg.steps['0'].dof = 'Tx_Ty_Tz_Rx_Ry_Rz_Sz'
        # add user parameters
        for paramStep in arguments['-param']:
            paramreg.addStep(paramStep)
    else:
        paramreg = initMultiStep()
        # if ref=subject, initialize registration using different affine parameters
        if ref == 'subject':
            paramreg.steps['0'].dof = 'Tx_Ty_Tz_Rx_Ry_Rz_Sz'

    # initialize other parameters
    # file_template_label = param.file_template_label
    zsubsample = param.zsubsample
    template = os.path.basename(os.path.normpath(path_template))
    # smoothing_sigma = param.smoothing_sigma

    # retrieve template file names
    file_template_vertebral_labeling = sct_warp_template.get_file_label(
        path_template + 'template/', 'vertebral')
    file_template = sct_warp_template.get_file_label(path_template + 'template/',
                                   contrast_template.upper() + '-weighted')
    file_template_seg = sct_warp_template.get_file_label(path_template + 'template/',
                                       'spinal cord')

    # start timer
    start_time = time.time()

    # get fname of the template + template objects
    fname_template = path_template + 'template/' + file_template
    fname_template_vertebral_labeling = path_template + 'template/' + file_template_vertebral_labeling
    fname_template_seg = path_template + 'template/' + file_template_seg

    # check file existence
    # TODO: no need to do that!
    sct.printv('\nCheck template files...')
    sct.check_file_exist(fname_template, verbose)
    sct.check_file_exist(fname_template_vertebral_labeling, verbose)
    sct.check_file_exist(fname_template_seg, verbose)

    # print arguments
    sct.printv('\nCheck parameters:', verbose)
    sct.printv('  Data:                 ' + fname_data, verbose)
    sct.printv('  Landmarks:            ' + fname_landmarks, verbose)
    sct.printv('  Segmentation:         ' + fname_seg, verbose)
    sct.printv('  Path template:        ' + path_template, verbose)
    sct.printv('  Remove temp files:    ' + str(remove_temp_files), verbose)

    # create QC folder
    sct.create_folder(param.path_qc)

    # check if data, segmentation and landmarks are in the same space
    sct.printv('\nCheck if data, segmentation and landmarks are in the same space...')
    path_data, file_data, ext_data = sct.extract_fname(fname_data)
    if not sct.check_if_same_space(fname_data, fname_seg):
        sct.printv(
            'ERROR: Data image and segmentation are not in the same space. Please check space and orientation of your files',
            verbose, 'error')
    if not sct.check_if_same_space(fname_data, fname_landmarks):
        sct.printv(
            'ERROR: Data image and landmarks are not in the same space. Please check space and orientation of your files',
            verbose, 'error')

    # check input labels
    labels = check_labels(fname_landmarks)

    # create temporary folder
    path_tmp = sct.tmp_create(verbose=verbose)

    # set temporary file names
    ftmp_data = 'data.nii'
    ftmp_seg = 'seg.nii.gz'
    ftmp_label = 'label.nii.gz'
    ftmp_template = 'template.nii'
    ftmp_template_seg = 'template_seg.nii.gz'
    ftmp_template_label = 'template_label.nii.gz'

    # copy files to temporary folder
    sct.printv('\nCopying input data to tmp folder and convert to nii...',
               verbose)
    sct.run('sct_convert -i ' + fname_data + ' -o ' + path_tmp + ftmp_data)
    sct.run('sct_convert -i ' + fname_seg + ' -o ' + path_tmp + ftmp_seg)
    sct.run('sct_convert -i ' + fname_landmarks + ' -o ' + path_tmp +
            ftmp_label)
    sct.run('sct_convert -i ' + fname_template + ' -o ' + path_tmp +
            ftmp_template)
    sct.run('sct_convert -i ' + fname_template_seg + ' -o ' + path_tmp +
            ftmp_template_seg)
    # sct.run('sct_convert -i '+fname_template_label+' -o '+path_tmp+ftmp_template_label)

    # go to tmp folder
    os.chdir(path_tmp)

    # Generate labels from template vertebral labeling
    sct.printv('\nGenerate labels from template vertebral labeling', verbose)
    sct.run('sct_label_utils -i ' + fname_template_vertebral_labeling +
            ' -vert-body 0 -o ' + ftmp_template_label)

    # check if provided labels are available in the template
    sct.printv('\nCheck if provided labels are available in the template',
               verbose)
    image_label_template = msct_image.Image(ftmp_template_label)
    labels_template = image_label_template.getNonZeroCoordinates(
        sorting='value')
    if labels[-1].value > labels_template[-1].value:
        sct.printv(
            'ERROR: Wrong landmarks input. Labels must have correspondence in template space. \nLabel max '
            'provided: ' + str(labels[-1].value) +
            '\nLabel max from template: ' + str(labels_template[-1].value),
            verbose, 'error')

    # binarize segmentation (in case it has values below 0 caused by manual editing)
    sct.printv('\nBinarize segmentation', verbose)
    sct.run('sct_maths -i seg.nii.gz -bin 0.5 -o seg.nii.gz')

    # Switch between modes: subject->template or template->subject
    if ref == 'template':
        # resample data to 1mm isotropic
        sct.printv('\nResample data to 1mm isotropic...', verbose)
        sct.run('sct_resample -i ' + ftmp_data +
                ' -mm 1.0x1.0x1.0 -x linear -o ' + sct.add_suffix(ftmp_data,
                                                              '_1mm'))
        ftmp_data = sct.add_suffix(ftmp_data, '_1mm')
        sct.run('sct_resample -i ' + ftmp_seg +
                ' -mm 1.0x1.0x1.0 -x linear -o ' + sct.add_suffix(ftmp_seg,
                                                              '_1mm'))
        ftmp_seg = sct.add_suffix(ftmp_seg, '_1mm')
        # N.B. resampling of labels is more complicated, because they are single-point labels, therefore resampling with neighrest neighbour can make them disappear. Therefore a more clever approach is required.
        resample_labels(ftmp_label, ftmp_data, sct.add_suffix(ftmp_label, '_1mm'))
        ftmp_label = sct.add_suffix(ftmp_label, '_1mm')

        # Change orientation of input images to RPI
        sct.printv('\nChange orientation of input images to RPI...', verbose)
        sct.run('sct_image -i ' + ftmp_data + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_data, '_rpi'))
        ftmp_data = sct.add_suffix(ftmp_data, '_rpi')
        sct.run('sct_image -i ' + ftmp_seg + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_seg, '_rpi'))
        ftmp_seg = sct.add_suffix(ftmp_seg, '_rpi')
        sct.run('sct_image -i ' + ftmp_label + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_label, '_rpi'))
        ftmp_label = sct.add_suffix(ftmp_label, '_rpi')

        # get landmarks in native space
        # crop segmentation
        # output: segmentation_rpi_crop.nii.gz
        status_crop, output_crop = sct.run(
            'sct_crop_image -i ' + ftmp_seg + ' -o ' + sct.add_suffix(
                ftmp_seg, '_crop') + ' -dim 2 -bzmax', verbose)
        ftmp_seg = sct.add_suffix(ftmp_seg, '_crop')
        cropping_slices = output_crop.split('Dimension 2: ')[1].split('\n')[
            0].split(' ')

        # straighten segmentation
        sct.printv(
            '\nStraighten the spinal cord using centerline/segmentation...',
            verbose)
        # check if warp_curve2straight and warp_straight2curve already exist (i.e. no need to do it another time)
        if os.path.isfile('../warp_curve2straight.nii.gz') and os.path.isfile(
                '../warp_straight2curve.nii.gz') and os.path.isfile(
                    '../straight_ref.nii.gz'):
            # if they exist, copy them into current folder
            sct.printv(
                'WARNING: Straightening was already run previously. Copying warping fields...',
                verbose, 'warning')
            shutil.copy('../warp_curve2straight.nii.gz',
                        'warp_curve2straight.nii.gz')
            shutil.copy('../warp_straight2curve.nii.gz',
                        'warp_straight2curve.nii.gz')
            shutil.copy('../straight_ref.nii.gz', 'straight_ref.nii.gz')
            # apply straightening
            sct.run('sct_apply_transfo -i ' + ftmp_seg +
                    ' -w warp_curve2straight.nii.gz -d straight_ref.nii.gz -o '
                    + sct.add_suffix(ftmp_seg, '_straight'))
        else:
            sct.run('sct_straighten_spinalcord -i ' + ftmp_seg + ' -s ' +
                    ftmp_seg + ' -o ' + sct.add_suffix(ftmp_seg, '_straight') +
                    ' -qc 0 -r 0 -v ' + str(verbose), verbose)
        # N.B. DO NOT UPDATE VARIABLE ftmp_seg BECAUSE TEMPORARY USED LATER
        # re-define warping field using non-cropped space (to avoid issue #367)
        sct.run('sct_concat_transfo -w warp_straight2curve.nii.gz -d ' +
                ftmp_data + ' -o warp_straight2curve.nii.gz')

        # Label preparation:
        # Remove unused label on template. Keep only label present in the input label image
        sct.printv(
            '\nRemove unused label on template. Keep only label present in the input label image...',
            verbose)
        sct.run('sct_label_utils -i ' + ftmp_template_label + ' -o ' +
                ftmp_template_label + ' -remove ' + ftmp_label)

        # Dilating the input label so they can be straighten without losing them
        sct.printv('\nDilating input labels using 3vox ball radius')
        sct.run('sct_maths -i ' + ftmp_label + ' -o ' + sct.add_suffix(
            ftmp_label, '_dilate') + ' -dilate 3')
        ftmp_label = sct.add_suffix(ftmp_label, '_dilate')

        # Apply straightening to labels
        sct.printv('\nApply straightening to labels...', verbose)
        sct.run('sct_apply_transfo -i ' + ftmp_label + ' -o ' + sct.add_suffix(
            ftmp_label, '_straight') + ' -d ' + sct.add_suffix(ftmp_seg,
                                                           '_straight') +
                ' -w warp_curve2straight.nii.gz -x nn')
        ftmp_label = sct.add_suffix(ftmp_label, '_straight')

        # Compute rigid transformation straight landmarks --> template landmarks
        sct.printv('\nEstimate transformation for step #0...', verbose)
        try:
           msct_register_landmarks.register_landmarks(
                ftmp_label,
                ftmp_template_label,
                paramreg.steps['0'].dof,
                fname_affine='straight2templateAffine.txt',
                verbose=verbose)
        except Exception:
            sct.printv(
                'ERROR: input labels do not seem to be at the right place. Please check the position of the labels. See documentation for more details: https://sourceforge.net/p/spinalcordtoolbox/wiki/create_labels/',
                verbose=verbose,
                type='error')

        # Concatenate transformations: curve --> straight --> affine
        sct.printv(
            '\nConcatenate transformations: curve --> straight --> affine...',
            verbose)
        sct.run(
            'sct_concat_transfo -w warp_curve2straight.nii.gz,straight2templateAffine.txt -d template.nii -o warp_curve2straightAffine.nii.gz'
        )

        # Apply transformation
        sct.printv('\nApply transformation...', verbose)
        sct.run('sct_apply_transfo -i ' + ftmp_data + ' -o ' + sct.add_suffix(
            ftmp_data, '_straightAffine') + ' -d ' + ftmp_template +
                ' -w warp_curve2straightAffine.nii.gz')
        ftmp_data = sct.add_suffix(ftmp_data, '_straightAffine')
        sct.run('sct_apply_transfo -i ' + ftmp_seg + ' -o ' + sct.add_suffix(
            ftmp_seg, '_straightAffine') + ' -d ' + ftmp_template +
                ' -w warp_curve2straightAffine.nii.gz -x linear')
        ftmp_seg = sct.add_suffix(ftmp_seg, '_straightAffine')

        # binarize
        sct.printv('\nBinarize segmentation...', verbose)
        sct.run('sct_maths -i ' + ftmp_seg + ' -bin 0.5 -o ' + sct.add_suffix(
            ftmp_seg, '_bin'))
        ftmp_seg = sct.add_suffix(ftmp_seg, '_bin')

        # find min-max of anat2template (for subsequent cropping)
        seg_template = sct_crop_image.main(['-i', str(ftmp_seg),
                                             '-dim', '2',
                                             '-bmax',
                                             '-o', 'tmp.nii'], do_return=True)

        # crop template in z-direction (for faster processing)
        sct.printv('\nCrop data in template space (for faster processing)...',
                   verbose)
        sct.run('sct_crop_image -i ' + ftmp_template + ' -o ' + sct.add_suffix(
            ftmp_template, '_crop') + ' -dim 2 -start ' + str(seg_template.zmin) +
                ' -end ' + str(seg_template.zmax))
        ftmp_template = sct.add_suffix(ftmp_template, '_crop')
        sct.run('sct_crop_image -i ' + ftmp_template_seg + ' -o ' + sct.add_suffix(
            ftmp_template_seg, '_crop') + ' -dim 2 -start ' + str(
                seg_template.zmin) + ' -end ' + str(seg_template.zmax))
        ftmp_template_seg = sct.add_suffix(ftmp_template_seg, '_crop')
        sct.run('sct_crop_image -i ' + ftmp_data + ' -o ' + sct.add_suffix(
            ftmp_data, '_crop') + ' -dim 2 -start ' + str(seg_template.zmin) +
                ' -end ' + str(seg_template.zmax))
        ftmp_data = sct.add_suffix(ftmp_data, '_crop')
        sct.run('sct_crop_image -i ' + ftmp_seg + ' -o ' + sct.add_suffix(
            ftmp_seg, '_crop') + ' -dim 2 -start ' + str(seg_template.zmin) +
                ' -end ' + str(seg_template.zmax))
        ftmp_seg = sct.add_suffix(ftmp_seg, '_crop')

        # sub-sample in z-direction
        sct.printv('\nSub-sample in z-direction (for faster processing)...',
                   verbose)
        sct.run('sct_resample -i ' + ftmp_template + ' -o ' + sct.add_suffix(
            ftmp_template, '_sub') + ' -f 1x1x' + zsubsample, verbose)
        ftmp_template = sct.add_suffix(ftmp_template, '_sub')
        sct.run('sct_resample -i ' + ftmp_template_seg + ' -o ' + sct.add_suffix(
            ftmp_template_seg, '_sub') + ' -f 1x1x' + zsubsample, verbose)
        ftmp_template_seg = sct.add_suffix(ftmp_template_seg, '_sub')
        sct.run('sct_resample -i ' + ftmp_data + ' -o ' + sct.add_suffix(
            ftmp_data, '_sub') + ' -f 1x1x' + zsubsample, verbose)
        ftmp_data = sct.add_suffix(ftmp_data, '_sub')
        sct.run('sct_resample -i ' + ftmp_seg + ' -o ' + sct.add_suffix(
            ftmp_seg, '_sub') + ' -f 1x1x' + zsubsample, verbose)
        ftmp_seg = sct.add_suffix(ftmp_seg, '_sub')

        # Registration straight spinal cord to template
        sct.printv('\nRegister straight spinal cord to template...', verbose)

        # loop across registration steps
        warp_forward = []
        warp_inverse = []
        for i_step in range(1, len(paramreg.steps)):
            sct.printv(
                '\nEstimate transformation for step #' + str(i_step) + '...',
                verbose)
            # identify which is the src and dest
            if paramreg.steps[str(i_step)].type == 'im':
                src = ftmp_data
                dest = ftmp_template
                interp_step = 'linear'
            elif paramreg.steps[str(i_step)].type == 'seg':
                src = ftmp_seg
                dest = ftmp_template_seg
                interp_step = 'nn'
            else:
                sct.printv('ERROR: Wrong image type.', 1, 'error')
            # if step>1, apply warp_forward_concat to the src image to be used
            if i_step > 1:
                # apply transformation from previous step, to use as new src for registration
                sct.run('sct_apply_transfo -i ' + src + ' -d ' + dest + ' -w '
                        + ','.join(warp_forward) + ' -o ' + sct.add_suffix(
                            src, '_regStep' + str(i_step - 1)) + ' -x ' +
                        interp_step, verbose)
                src = sct.add_suffix(src, '_regStep' + str(i_step - 1))
            # register src --> dest
            # TODO: display param for debugging
            warp_forward_out, warp_inverse_out = sct_register_multimodal.register(src, dest, paramreg,
                                                          param, str(i_step))
            warp_forward.append(warp_forward_out)
            warp_inverse.append(warp_inverse_out)

        # Concatenate transformations:
        sct.printv('\nConcatenate transformations: anat --> template...',
                   verbose)
        sct.run('sct_concat_transfo -w warp_curve2straightAffine.nii.gz,' +
                ','.join(warp_forward) +
                ' -d template.nii -o warp_anat2template.nii.gz', verbose)
        sct.printv('\nConcatenate transformations: template --> anat...',
                   verbose)
        warp_inverse.reverse()
        sct.run(
            'sct_concat_transfo -w ' + ','.join(warp_inverse) +
            ',-straight2templateAffine.txt,warp_straight2curve.nii.gz -d data.nii -o warp_template2anat.nii.gz',
            verbose)

    # register template->subject
    elif ref == 'subject':
        # Change orientation of input images to RPI
        sct.printv('\nChange orientation of input images to RPI...', verbose)
        sct.run('sct_image -i ' + ftmp_data + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_data, '_rpi'))
        ftmp_data = sct.add_suffix(ftmp_data, '_rpi')
        sct.run('sct_image -i ' + ftmp_seg + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_seg, '_rpi'))
        ftmp_seg = sct.add_suffix(ftmp_seg, '_rpi')
        sct.run('sct_image -i ' + ftmp_label + ' -setorient RPI -o ' +
                sct.add_suffix(ftmp_label, '_rpi'))
        ftmp_label = sct.add_suffix(ftmp_label, '_rpi')

        # Remove unused label on template. Keep only label present in the input label image
        sct.printv(
            '\nRemove unused label on template. Keep only label present in the input label image...',
            verbose)
        sct.run('sct_label_utils -i ' + ftmp_template_label + ' -o ' +
                ftmp_template_label + ' -remove ' + ftmp_label)

        # Add one label because at least 3 orthogonal labels are required to estimate an affine transformation. This new label is added at the level of the upper most label (lowest value), at 1cm to the right.
        for i_file in [ftmp_label, ftmp_template_label]:
            im_label = msct_image.Image(i_file)
            coord_label = im_label.getCoordinatesAveragedByValue(
            )  # N.B. landmarks are sorted by value
            # Create new label
            from copy import deepcopy
            new_label = deepcopy(coord_label[0])
            # move it 5mm to the left (orientation is RAS)
            nx, ny, nz, nt, px, py, pz, pt = im_label.dim
            new_label.x = round(coord_label[0].x + 5.0 / px)
            # assign value 99
            new_label.value = 99
            # Add to existing image
            im_label.data[int(new_label.x), int(new_label.y), int(new_label.z)] = new_label.value
            # Overwrite label file
            # im_label.setFileName('label_rpi_modif.nii.gz')
            im_label.save()

        # Bring template to subject space using landmark-based transformation
        sct.printv('\nEstimate transformation for step #0...', verbose)
        warp_forward = ['template2subjectAffine.txt']
        warp_inverse = ['-template2subjectAffine.txt']
        try:
           msct_register_landmarks.register_landmarks(
                ftmp_template_label,
                ftmp_label,
                paramreg.steps['0'].dof,
                fname_affine=warp_forward[0],
                verbose=verbose,
                path_qc=param.path_qc)
        except Exception:
            sct.printv(
                'ERROR: input labels do not seem to be at the right place. Please check the position of the labels. See documentation for more details: https://sourceforge.net/p/spinalcordtoolbox/wiki/create_labels/',
                verbose=verbose,
                type='error')

        # loop across registration steps
        for i_step in range(1, len(paramreg.steps)):
            sct.printv(
                '\nEstimate transformation for step #' + str(i_step) + '...',
                verbose)
            # identify which is the src and dest
            if paramreg.steps[str(i_step)].type == 'im':
                src = ftmp_template
                dest = ftmp_data
                interp_step = 'linear'
            elif paramreg.steps[str(i_step)].type == 'seg':
                src = ftmp_template_seg
                dest = ftmp_seg
                interp_step = 'nn'
            else:
                sct.printv('ERROR: Wrong image type.', 1, 'error')
            # apply transformation from previous step, to use as new src for registration
            sct.run(
                'sct_apply_transfo -i ' + src + ' -d ' + dest + ' -w ' +
                ','.join(warp_forward) + ' -o ' + sct.add_suffix(
                    src, '_regStep' + str(i_step - 1)) + ' -x ' + interp_step,
                verbose)
            src = sct.add_suffix(src, '_regStep' + str(i_step - 1))
            # register src --> dest
            # TODO: display param for debugging
            warp_forward_out, warp_inverse_out = sct_register_multimodal.register(src, dest, paramreg,
                                                          param, str(i_step))
            warp_forward.append(warp_forward_out)
            warp_inverse.insert(0, warp_inverse_out)

        # Concatenate transformations:
        sct.printv('\nConcatenate transformations: template --> subject...',
                   verbose)
        sct.run('sct_concat_transfo -w ' + ','.join(warp_forward) +
                ' -d data.nii -o warp_template2anat.nii.gz', verbose)
        sct.printv('\nConcatenate transformations: subject --> template...',
                   verbose)
        sct.run('sct_concat_transfo -w ' + ','.join(warp_inverse) +
                ' -d template.nii -o warp_anat2template.nii.gz', verbose)

    # Apply warping fields to anat and template
    sct.run(
        'sct_apply_transfo -i template.nii -o template2anat.nii.gz -d data.nii -w warp_template2anat.nii.gz -crop 1',
        verbose)
    sct.run(
        'sct_apply_transfo -i data.nii -o anat2template.nii.gz -d template.nii -w warp_anat2template.nii.gz -crop 1',
        verbose)

    # come back to parent folder
    os.chdir('..')

    # Generate output files
    sct.printv('\nGenerate output files...', verbose)
    sct.generate_output_file(path_tmp + 'warp_template2anat.nii.gz',
                             path_output + 'warp_template2anat.nii.gz',
                             verbose)
    sct.generate_output_file(path_tmp + 'warp_anat2template.nii.gz',
                             path_output + 'warp_anat2template.nii.gz',
                             verbose)
    sct.generate_output_file(path_tmp + 'template2anat.nii.gz',
                             path_output + 'template2anat' + ext_data, verbose)
    sct.generate_output_file(path_tmp + 'anat2template.nii.gz',
                             path_output + 'anat2template' + ext_data, verbose)
    if ref == 'template':
        # copy straightening files in case subsequent SCT functions need them
        sct.generate_output_file(path_tmp + 'warp_curve2straight.nii.gz',
                                 path_output + 'warp_curve2straight.nii.gz',
                                 verbose)
        sct.generate_output_file(path_tmp + 'warp_straight2curve.nii.gz',
                                 path_output + 'warp_straight2curve.nii.gz',
                                 verbose)
        sct.generate_output_file(path_tmp + 'straight_ref.nii.gz',
                                 path_output + 'straight_ref.nii.gz', verbose)

    # Delete temporary files
    if remove_temp_files:
        sct.printv('\nDelete temporary files...', verbose)
        shutil.rmtree(path_tmp, ignore_errors=True)

    # display elapsed time
    elapsed_time = time.time() - start_time
    sct.printv(
        '\nFinished! Elapsed time: ' + str(int(round(elapsed_time))) + 's',
        verbose)

    # to view results
    sct.printv('\nTo view results, type:', verbose)
    sct.printv('fslview ' + fname_data + ' ' + path_output +
               'template2anat -b 0,4000 &', verbose, 'info')
    sct.printv('fslview ' + fname_template + ' -b 0,5000 ' + path_output +
               'anat2template &\n', verbose, 'info')


def resample_labels(fname_labels, fname_dest, fname_output):
    """
    This function re-create labels into a space that has been resampled. It works by re-defining the location of each
    label using the old and new voxel size.
    """
    # get dimensions of input and destination files
    nx, ny, nz, nt, px, py, pz, pt = msct_image.Image(fname_labels).dim
    nxd, nyd, nzd, ntd, pxd, pyd, pzd, ptd = msct_image.Image(fname_dest).dim
    sampling_factor = [float(nx) / nxd, float(ny) / nyd, float(nz) / nzd]
    # read labels
    processor = sct_label_utils.ProcessLabels(fname_labels)
    label_list = processor.display_voxel()
    label_new_list = []
    for label in label_list:
        label_sub_new = [
            str(int(round(int(label.x) / sampling_factor[0]))),
            str(int(round(int(label.y) / sampling_factor[1]))),
            str(int(round(int(label.z) / sampling_factor[2]))),
            str(int(float(label.value)))
        ]
        label_new_list.append(','.join(label_sub_new))
    label_new_list = ':'.join(label_new_list)
    # create new labels
    sct.run('sct_label_utils -i ' + fname_dest + ' -create ' + label_new_list +
            ' -v 1 -o ' + fname_output)

def check_labels(fname_landmarks):
    """
    Make sure input labels are consistent
    Parameters
    ----------
    fname_landmarks: file name of input labels

    Returns
    -------
    none
    """
    sct.printv('\nCheck input labels...')
    # open label file
    image_label = msct_image.Image(fname_landmarks)
    # -> all labels must be different
    labels = image_label.getNonZeroCoordinates(sorting='value')
    # check if there is two labels
    if not len(labels) == 2:
        sct.printv('ERROR: Label file has ' + str(len(labels)) + ' label(s). It must contain exactly two labels.', 1, 'error')
    # check if the two labels are integer
    for label in labels:
        if not int(label.value) == label.value:
            sct.printv('ERROR: Label should be integer.', 1, 'error')
    # check if the two labels are different
    if labels[0].value == labels[1].value:
        sct.printv('ERROR: The two labels must be different.', 1, 'error')
    return labels


if __name__ == "__main__":
    main()
