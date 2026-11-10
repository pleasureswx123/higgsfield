import { request } from './client'
export interface Profile {
  userName: string
  nickName: string
  phonenumber?: string | null
  email?: string | null
}
export interface ProfileInput { nickName: string; phonenumber: string; email: string }
export const getProfile = () => request<{ code: number; data: Profile }>({ url: '/system/user/profile' })
export const updateProfile = (data: ProfileInput) => request<{ code: number }>({ url: '/system/user/profile', method: 'PUT', data })
export const updatePassword = (data: { oldPassword: string; newPassword: string }) => request<{ code: number }>({ url: '/system/user/profile/updatePwd', method: 'PUT', data })
